from fastapi import FastAPI, Request, BackgroundTasks
import asyncio
import logging
import json
from typing import List
from app.monitoring_task import MonitoringTask
import sys
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import os


root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  
    ],
    force=True
)
logger = logging.getLogger(__name__)

monitoring_task = MonitoringTask()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Monitor and restart service started")
    yield
    for task in monitoring_task.active_tasks.values():
        task.cancel()
    logger.info("Monitor and restart service stopped")

app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def handle_webhook(request: Request):
    try:
        webhook_data = await request.json()
        logger.debug(f"Raw webhook data: {json.dumps(webhook_data, indent=2)}")
        
        monitor_name = webhook_data["monitor"]["name"]
        monitor_url = webhook_data["monitor"]["url"]
        monitor_msg = webhook_data.get("msg", "")
        monitor_pathName = webhook_data["monitor"]["pathName"]
        
        # Only trigger monitoring task if status is "Down"
        if "Down" in monitor_msg and "Active Miners" in monitor_pathName:
        
            # Check if there's already an active monitoring task for this URL
            if monitor_url not in monitoring_task.active_tasks:
                # Create new monitoring task
                
                task = asyncio.create_task(
                    monitoring_task.monitor_and_restart(monitor_url, monitor_name)
                )
                monitoring_task.active_tasks[monitor_url] = task
                logger.info(f"Started new monitoring task for {monitor_url}")
            else:
                logger.info(f"Monitoring task already active for {monitor_url}")

            return {
                "status": "success",
                "message": f"Monitoring initiated for {monitor_name}",
                "url": monitor_url
            }
        else:
            logger.info(f"Skipping monitoring task - no Down status detected for {monitor_name}")
            return {
                "status": "skipped",
                "message": f"No monitoring needed for {monitor_name} - status is not Down",
                "url": monitor_url
            }
        
    except Exception as e:
        error_msg = f"Error processing webhook: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"status": "error", "message": error_msg}
    
@app.post("/webhook/fetcher")
async def handle_webhook_fetcher(request: Request):
    try:
        # Check for bearer token in Authorization header
        logger.info(f"Received request:\n {request}")
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            logger.warning("Missing or invalid Authorization header")
            return {"status": "error", "message": "Missing or invalid bearer token"}, 401
        
        # Extract token (remove "Bearer " prefix)
        token = auth_header[7:]  # Skip "Bearer " (7 characters)
        
        load_dotenv()
        EXPECTED_TOKEN = os.getenv("API_TOKEN")
        EXPECTED_TOKEN = EXPECTED_TOKEN.strip('"').strip("'")

        if token != EXPECTED_TOKEN:
            logger.warning(f"Invalid bearer token provided: {token[:8]}...")
            logger.warning(f"Token received: {token}")
            logger.warning(f"Token expected: {EXPECTED_TOKEN}")
            return {"status": "error", "message": "Invalid bearer token"}, 401
        
        webhook_data = await request.json()
        logger.debug(f"Raw webhook data: {json.dumps(webhook_data, indent=2)}")
        
        monitor_name = webhook_data["name"]
        monitor_url = webhook_data["url"]                        
      
        await monitoring_task.restart_service(monitor_url, monitor_name)
        
        return {
            "status": "success",
            "message": f"Restart triggered for {monitor_name}",
            "url": monitor_url
        }        
        
    except Exception as e:
        error_msg = f"Error processing webhook: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"status": "error", "message": error_msg}

@app.post("/debug/webhook")
async def debug_webhook(request: Request):
    # Log headers
    logger.info("=== Headers ===")
    for header, value in request.headers.items():
        logger.info(f"{header}: {value}")

    # Log raw body
    body = await request.body()
    logger.info("\n=== Raw Body ===")
    logger.info(body.decode())

    # Log parsed JSON
    try:
        json_data = await request.json()
        logger.info("\n=== Parsed JSON ===")
        logger.info(json.dumps(json_data, indent=2))
    except Exception as e:
        logger.error(f"Error parsing JSON: {e}")
        json_data = {"error": "Could not parse JSON"}

    return {
        "status": "debug_received",
        "headers": dict(request.headers),
        "body": json_data
    }
