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
    def _init_subtensor_connection(self) -> None:
        for attempt in range(3):
            try:
                self.subtensor = bt.subtensor()
                self.metagraph = bt.metagraph(
                    netuid=6, lite=True, subtensor=self.subtensor
                )
                logger.info("Subtensor connection created")
                break
            except Exception as e:
                logger.warning(f"Failed to connect: {e} (Attempt {attempt + 1})")
                time.sleep(5)
        else:
            logger.error("Could not estabilsh connection with subtensor")

    def __init__(self) -> None:
        self._init_subtensor_connection()

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

def load_hosts(api, config_folder='../config_fetcher/all_host_vars'):
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
        logger.warning("Active Miners group not found. Monitors will be created without a parent group.")
    
    # Process all YAML files in the config folder
    config_path = Path(config_folder)
    if not config_path.exists():
        logger.error(f"Config folder not found: {config_folder}")
        return
    
    yaml_files = list(config_path.glob('*.yml')) + list(config_path.glob('*.yaml'))
    
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
                    'active': True,
                    'description': description
                }
                
                # Add to Active Miners group if it exists
                if active_group_id:
                    monitor_data['parent'] = active_group_id
                
                # Add tags based on provider
                monitor_data['tags'] = [
                    {'name': provider, 'color': '#0000FF'},
                    {'name': 'miner', 'color': '#00FF00'}
                ]
                
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
                            logger.info(f"Updated monitor: {miner_name} (ID: {monitor_id}) - Fields: {list(update_fields.keys())}")
                        except Exception as e:
                            logger.error(f"Error updating monitor {miner_name}: {e}")
                    else:
                        logger.info(f"Monitor already up to date: {miner_name}")
                else:
                    # Create new monitor
                    try:
                        response = api.add_monitor(**monitor_data)
                        monitor_id = response.get('monitorID')
                        logger.info(f"Created monitor: {miner_name} (ID: {monitor_id})")
                        
                        # Add custom properties as tags or in description
                        # Since Uptime Kuma doesn't support arbitrary custom fields,
                        # we can encode the config in the description or use tags
                        if miner.get('config'):
                            # You might want to store important config values as tags
                            # or append them to the description
                            pass
                            
                    except Exception as e:
                        logger.error(f"Error creating monitor {miner_name}: {e}")
                    
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

    # Get active endpoints from metagraph
    active_hotkeys = bt_conn.get_active_hotkeys()

    hk_map = load_hotkeys()

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
            if hkey:
                is_active = hkey in active_hotkeys
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
            logging.error(f"Error processing monitor {monitor['name']}: {str(e)}")

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
        load_default_groups_and_notifications(api)_
        
        update_miner_groups(api, bt_conn)
    except Exception as e:
        logging.error(f"Error: {str(e)}")
    finally:
        api.disconnect()

def main():

    logging.info("Auto updater started")
    bt_conn = BittensorConnection()
    job(bt_conn)
    logging.info("Finished initial update.")

    interval_mins = int(os.getenv("UPDATE_INTERVAL_MIN", "15"))
    logging.info(f"Update interval: {interval_mins} min")

    schedule.every(2).minutes.do(lambda: job(bt_conn))


    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
