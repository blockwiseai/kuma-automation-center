import logging
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from sync_config import fetch_and_save

logger = logging.getLogger("config-fetcher-scheduler")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
logger.setLevel(logging.INFO)

def start_scheduler() -> None:
    scheduler = BlockingScheduler()
    scheduler.add_job(fetch_and_save, "interval", minutes=15, next_run_time=datetime.now())
    scheduler.start()


if __name__ == "__main__":
    start_scheduler()
