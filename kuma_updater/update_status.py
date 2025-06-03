import csv
import hashlib
import logging
import os
import time

import bittensor as bt
import requests
import schedule
from uptime_kuma_api import UptimeKumaApi

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
        update_miner_groups(api, bt_conn)
    except Exception as e:
        logging.error(f"Error: {str(e)}")
    finally:
        api.disconnect()


def send_heartbeat():
    url = "https://glitchtip.s6bw.ip-ddns.com/api/0/organizations/blockwise/heartbeat_check/77c14da8-0c16-4f54-816e-e017573a7cad/"
    try:
        response = requests.post(url, verify=False)
        logging.info(
            f"Heartbeat sent at {time.strftime('%H:%M:%S')}, Status: {response.status_code}"
        )
    except Exception as e:
        logging.error(f"Error sending heartbeat: {e}")


def main():
    import sentry_sdk

    sentry_sdk.init(
        dsn="https://954714da13e5494ea9bec6a88dfd9a60@glitchtip.s6bw.ip-ddns.com/3",
        traces_sample_rate=1.0,
        enable_tracing=True,
    )
    send_heartbeat()

    logging.info("Auto updater started")
    bt_conn = BittensorConnection()
    job(bt_conn)
    logging.info("Finished initial update.")

    interval_mins = int(os.getenv("UPDATE_INTERVAL_MIN", "15"))
    logging.info(f"Update interval: {interval_mins} min")

    schedule.every(2).minutes.do(lambda: job(bt_conn))
    schedule.every(10).minutes.do(send_heartbeat)

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
