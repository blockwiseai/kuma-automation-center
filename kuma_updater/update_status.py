import csv
import hashlib
import logging
import os
import time

import bittensor as bt
import requests
import schedule
from pathlib import Path
from uptime_kuma_api import UptimeKumaApi, MonitorType, NotificationType
import yaml

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger()


class BittensorConnection:
    def _init_subtensor_connection(self, netuid) -> None:
        for attempt in range(3):
            try:
                self.subtensor = bt.subtensor()
                self.metagraph = bt.metagraph(
                    netuid=netuid, lite=True, subtensor=self.subtensor
                )
                logger.info("Subtensor connection created")
                break
            except Exception as e:
                logger.warning(
                    f"Failed to connect: {e} (Attempt {attempt + 1})")
                time.sleep(5)
        else:
            logger.error("Could not estabilsh connection with subtensor")

    def __init__(self, netuid) -> None:
        self._init_subtensor_connection(netuid)

    def safe_sync(self) -> None:
        try:
            logger.debug("Syncing with metagraph")
            self.metagraph.sync()
        except Exception as e:
            logger.error(
                f"Could not sync with metagraph: {e}, trying to create new connection..."
            )
            self._init_subtensor_connection()

    def get_active_hotkeys(self):
        self.safe_sync()
        active_hotkeys = set()

        for hotkey in self.metagraph.hotkeys:
            active_hotkeys.add(hashlib.sha256(hotkey.encode()).hexdigest())

        return active_hotkeys

    def get_active_axons(self):
        self.safe_sync()
        active_axons = set()
        for axon in self.metagraph.addresses:
            active_axons.add(axon)


def find_group_id(monitors, group_name):
    for monitor in monitors:
        if monitor["type"] == "group" and monitor["name"] == group_name:
            return monitor["id"]
    return None


def load_hotkeys(csv_filename="hotkeys.csv"):
    """Loads hotkey_name and hkey_hash from a CSV file into a dictionary."""
    hotkey_map = {}
    try:
        with open(csv_filename, mode="r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if "hotkey_name" in row and "hkey_hash" in row:
                    hotkey_map[row["hotkey_name"]] = row["hkey_hash"]
    except FileNotFoundError:
        print(f"Error: {csv_filename} not found.")
    return hotkey_map


def setup_email_notification(api):
    """Setup email notification if configured"""
    # Get email configuration from environment
    email_to = os.getenv('NOTIFICATION_MAIL')
    
    # Check if email is configured
    if not email_to:
        logger.info("EMAIL_TO not configured, skipping email notification setup")
        return None
    
    try:
        # Check if email notification already exists
        notifications = api.get_notifications()
        email_notification_name = "Miner Status Email Alerts"
        
        for notif in notifications:
            if notif.get('name') == email_notification_name:
                logger.info(f"Email notification already exists: {email_notification_name}")
                return notif.get('id')
        
        # Create minimal email notification using local mail agent
        notification_data = {
            'name': email_notification_name,
            'type': NotificationType.SMTP,
            'hostname': 'localhost',  # Use local mail agent
            'port': 25,  # Standard SMTP port
            'security': 'none',  # No security for localhost
            'ignoreTLSError': True,
            'username': '',  # No auth needed for localhost
            'password': '',  # No auth needed for localhost
            'fromEmail': f'uptime-kuma@{os.uname().nodename}',  # Use hostname
            'toEmail': email_to,
            'isDefault': True,
            'applyExisting': True  # Apply to all existing monitors
        }
        
        response = api.add_notification(**notification_data)
        notification_id = response.get('id')
        logger.info(f"Created email notification: {email_notification_name} (ID: {notification_id})")
        return notification_id
        
    except Exception as e:
        logger.error(f"Error setting up email notification: {e}")
        return None


def load_default_groups_and_notifications(api):
    """Initialize default groups and notifications in Uptime Kuma"""

    # Get existing monitors to check for duplicates
    existing_monitors = api.get_monitors()

    # Create default groups if they don't exist
    groups_to_create = [
        {'name': 'Active Miners', 'active': True},
        {'name': 'Inactive Miners', 'active': False}
    ]
    created_groups = {}

    for group in groups_to_create:
        group_name = group['name']
        group_active = group['active']
        group_id = find_group_id(existing_monitors, group_name)

        if not group_id:
            try:
                # Create group monitor - only pass supported parameters for creation
                group_data = {
                    'type': MonitorType.GROUP,
                    'name': group_name
                }
                response = api.add_monitor(**group_data)
                group_id = response.get('monitorID')
                created_groups[group_name] = group_id
                logger.info(f"Created group: {group_name} (ID: {group_id})")

                try:
                    if not group_active:
                        api.pause_monitor(group_id)
                        logger.info(f"Set group {group_name} to inactive")
                except AttributeError:
                    try:
                        api.edit_monitor(group_id, active=group_active)
                        logger.info(
                            f"Set group {group_name} active state to: {group_active}")
                    except Exception as e:
                        logger.warning(
                            f"Could not set active state for {group_name}: {e}")

            except Exception as e:
                logger.error(f"Error creating group {group_name}: {e}")
        else:
            created_groups[group_name] = group_id
            logger.info(f"Group already exists: {group_name} (ID: {group_id})")

    # Setup webhook notification for Active Miners group
    if 'Active Miners' in created_groups:
        try:
            # Check if notifications already exist
            notifications = api.get_notifications()

            # Create webhook notification if it doesn't exist
            webhook_name = "Active Miners Webhook"
            webhook_exists = any(notif.get('name') ==
                                 webhook_name for notif in notifications)

            if not webhook_exists:
                # You'll need to configure this webhook URL
                webhook_url = os.environ.get(
                    'WEBHOOK_URL', 'https://example.com/webhook')

                notification_data = {
                    'name': webhook_name,
                    'type': NotificationType.WEBHOOK,
                    'webhookURL': webhook_url,
                    'webhookContentType': 'application/json',
                    'isDefault': True,
                    'applyExisting': False
                }

                notification_response = api.add_notification(
                    **notification_data)
                notification_id = notification_response.get('id')

                # Apply notification to Active Miners group
                if notification_id:
                    # This might need adjustment based on the API version
                    # Some versions might require different approach to link notifications to groups
                    logger.info(
                        f"Created webhook notification: {webhook_name}")
                    logger.info(f"Notification ID: {notification_id}")
            else:
                logger.info(
                    f"Webhook notification already exists: {webhook_name}")

        except Exception as e:
            logger.error(f"Error setting up webhook notification: {e}")
    
    # Setup email notification
    setup_email_notification(api)


def load_hosts(api, config_folder=os.path.join(os.getcwd(), 'host_vars/')):
    """Load monitors from YAML configuration files"""

    # Get existing monitors
    existing_monitors = api.get_monitors()
    existing_monitors_by_name = {
        monitor.get('name'): monitor
        for monitor in existing_monitors
        if monitor.get('type') != 'group'
    }

    # Get Active Miners group ID
    active_group_id = find_group_id(existing_monitors, 'Active Miners')

    if not active_group_id:
        logger.warning(
            "Active Miners group not found. Monitors will be created without a parent group.")

    # Process all YAML files in the config folder
    config_path = Path(config_folder)
    if not config_path.exists():

        logger.error(f"Config folder not found: {config_folder}")
        return

    yaml_files = list(config_path.glob('*.yml')) + \
        list(config_path.glob('*.yaml'))

    logger.info(f"FOUND YAML FILES: {yaml_files}")

    for yaml_file in yaml_files:
        try:
            with open(yaml_file, 'r') as f:
                config = yaml.safe_load(f)

            if not config or 'miners' not in config:
                logger.warning(f"No miners found in {yaml_file}")
                continue

            ansible_host = config.get('ansible_host', 'unknown')
            provider = config.get('provider', 'unknown')

            # Process each miner
            for miner in config['miners']:
                miner_name = miner.get('name')
                if not miner_name:
                    logger.warning(f"Miner without name in {yaml_file}")
                    continue

                # Prepare monitor data
                port = miner.get('port', '8080')
                branch = miner.get('branch', '')
                url = f"http://{ansible_host}:{port}"
                description = f"Provider: {provider}\nBranch: {branch}"

                monitor_data = {
                    'type': MonitorType.HTTP,
                    'name': miner_name,
                    'url': url,
                    'interval': 60,  # Check every 60 seconds
                    'retryInterval': 60,
                    'maxretries': 3,
                    'accepted_statuscodes': ["200-299"],
                    'description': description
                }

                # Add to Active Miners group if it exists
                if active_group_id:
                    monitor_data['parent'] = active_group_id

                # Add tags based on provider
                # monitor_data['tags'] = [
                #    {'name': provider, 'color': '#0000FF'},
                #    {'name': 'miner', 'color': '#00FF00'}
                # ]

                # Check if monitor already exists
                if miner_name in existing_monitors_by_name:
                    existing_monitor = existing_monitors_by_name[miner_name]
                    monitor_id = existing_monitor.get('id')

                    # Check if update is needed
                    needs_update = False
                    update_fields = {}

                    # Check each field for differences
                    if existing_monitor.get('url') != url:
                        update_fields['url'] = url
                        needs_update = True

                    if existing_monitor.get('description') != description:
                        update_fields['description'] = description
                        needs_update = True

                    if existing_monitor.get('interval') != 60:
                        update_fields['interval'] = 60
                        needs_update = True

                    if existing_monitor.get('retryInterval') != 60:
                        update_fields['retryInterval'] = 60
                        needs_update = True

                    if existing_monitor.get('maxretries') != 3:
                        update_fields['maxretries'] = 3
                        needs_update = True

                    # Check if parent group needs update
                    if active_group_id and existing_monitor.get('parent') != active_group_id:
                        update_fields['parent'] = active_group_id
                        needs_update = True

                    if needs_update:
                        try:
                            # Update the monitor
                            api.edit_monitor(monitor_id, **update_fields)
                            logger.info(
                                f"Updated monitor: {miner_name} (ID: {monitor_id}) - Fields: {list(update_fields.keys())}")
                        except Exception as e:
                            logger.error(
                                f"Error updating monitor {miner_name}: {e}")
                    else:
                        logger.info(
                            f"Monitor already up to date: {miner_name}")
                else:
                    # Create new monitor
                    try:
                        response = api.add_monitor(**monitor_data)
                        monitor_id = response.get('monitorID')
                        logger.info(
                            f"Created monitor: {miner_name} (ID: {monitor_id})")

                        # Add custom properties as tags or in description
                        # Since Uptime Kuma doesn't support arbitrary custom fields,
                        # we can encode the config in the description or use tags
                        if miner.get('config'):
                            # You might want to store important config values as tags
                            # or append them to the description
                            pass

                    except Exception as e:
                        logger.error(
                            f"Error creating monitor {miner_name}: {e}")

        except Exception as e:
            logger.error(f"Error processing {yaml_file}: {e}")


def update_miner_groups(api, bt_conn):
    # Get current monitors
    monitors = api.get_monitors()

    # Find group IDs
    active_group_id = find_group_id(monitors, "Active Miners")
    inactive_group_id = find_group_id(monitors, "Inactive Miners")

    if not active_group_id or not inactive_group_id:
        logging.error("Error: Could not find required groups")
        return

    hk_map = load_hotkeys()

    # Get active endpoints from metagraph
    active_hotkeys = bt_conn.get_active_hotkeys()
    deduct_monitor_from_axon = False
    if not hk_map:
        active_axons = bt_conn.get_active_axons()
        deduct_monitor_from_axon = True

    logging.info(f"Found {len(active_hotkeys)} active hotkeys in metagraph")

    moves_to_active = 0
    moves_to_inactive = 0

    for monitor in monitors:
        if monitor["type"] != "http" or monitor.get("parent") not in [
            active_group_id,
            inactive_group_id,
        ]:
            continue

        try:
            name = monitor["name"]
            hkey = hk_map.get(name, None)

            url = monitor["url"]
            # escape protocol from url
            parts = url.split("://")
            if len(parts) > 1:
                ip = parts[1]
            else:
                ip = url

            if hkey:
                is_active = hkey in active_hotkeys
                if deduct_monitor_from_axon:
                    is_active = ip in active_axons
            else:
                is_active = False
                logging.info(f"Hotkey missing in config file")
            current_parent = monitor["parent"]

            if is_active and current_parent != active_group_id:
                api.edit_monitor(monitor["id"], parent=active_group_id)
                moves_to_active += 1
                logging.info(f"Moved {monitor['name']} to Active Miners")
            elif not is_active and current_parent != inactive_group_id:
                api.edit_monitor(monitor["id"], parent=inactive_group_id)
                moves_to_inactive += 1
                logging.info(f"Moved {monitor['name']} to Inactive Miners")

        except Exception as e:
            logging.error(
                f"Error processing monitor {monitor['name']}: {str(e)}")

    logging.info(
        f"Updates complete: {moves_to_active} moved to active, {moves_to_inactive} moved to inactive"
    )


def job(bt_conn):
    kuma_url = os.getenv("KUMA_URL", "http://live-kuma:3001")
    kuma_user = os.getenv("KUMA_USER", "admin")
    kuma_pass = os.getenv("KUMA_PASS")

    if not kuma_pass:
        logging.error("Error: KUMA_PASS environment variable not set")
        return

    api = UptimeKumaApi(kuma_url)

    try:
        api.login(kuma_user, kuma_pass)
        load_default_groups_and_notifications(api)
        load_hosts(api)

        update_miner_groups(api, bt_conn)
    except Exception as e:
        logging.error(f"Error: {str(e)}")
    finally:
        api.disconnect()


def main():

    logging.info("Auto updater started")
    netuid = int(os.getenv("NETUID", "6"))
    bt_conn = BittensorConnection(netuid)
    job(bt_conn)
    logging.info("Finished initial update.")

    interval_mins = int(os.getenv("UPDATE_INTERVAL_MIN", "2"))
    logging.info(f"Update interval: {interval_mins} min")

    schedule.every(interval_mins).minutes.do(lambda: job(bt_conn))

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()