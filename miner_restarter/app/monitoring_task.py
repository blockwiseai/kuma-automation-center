import asyncio
import aiohttp
import asyncssh
import logging
from pydantic_settings import BaseSettings
from typing import Dict, List
from pydantic import Field
from datetime import datetime
from app.webhook_handler import send_notification_to_all
import sys
from dotenv import load_dotenv
import os


class Settings(BaseSettings):
    load_dotenv("config")
    SSH_USERNAME: str = os.environ.get("SSH_USERNAME", "miner-restarter")
    SSH_KEY_PATH: str = os.environ.get("SSH_KEY_PATH", "./app/miner-restarter")
    CHECK_INTERVAL: int = int(os.environ.get(
        "CHECK_INTERVAL", 1200))  # 5 minutes in seconds
    CHECK_COUNT: int = int(os.environ.get("CHECK_COUNT", 3))
    TIMEOUT_THRESHOLD: int = int(os.environ.get(
        "TIMEOUT_THRESHOLD", 3600))  # seconds
    # AWS_IPS =["98.80.70.48","34.238.193.115"]


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)
settings = Settings()


class MonitoringTask:
    def __init__(self):
        self.active_tasks: Dict[str, asyncio.Task] = {}

    async def check_endpoint(self, url: str, timeout: int = 60) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=timeout) as response:
                    return response.status in range(200, 299) or response.status in range(400, 499)
        except asyncio.TimeoutError:
            logger.info(f"Request to {url} timed out after {timeout} seconds")
            return False
        except Exception as e:
            logger.error(f"Error checking {url}: {str(e)}")
            return False

    def extract_hostname(self, url: str) -> str:
        """Extract hostname without port number from URL."""
        try:
            # Split URL into parts
            parts = url.split("://")
            if len(parts) > 1:
                # Take the part after protocol
                host_part = parts[1]
            else:
                host_part = parts[0]
            # Remove any path components
            host_part = host_part.split("/")[0]
            # Remove port if present
            hostname = host_part.split(":")[0]
            return hostname
        except Exception as e:
            logger.error(f"Error parsing hostname from URL {url}: {str(e)}")
            return url

    def get_sudo_username(self, hostname: str) -> str:

        # return 'ubuntu' if hostname in ["98.80.70.48","34.238.193.115"] else 'root'
        return 'miner'

    async def restart_service(self, hostname: str, service_name: str):
        try:
            clean_hostname = self.extract_hostname(hostname)
            sudo_username = self.get_sudo_username(clean_hostname)
            print(f"""Attempting to connect with:
                    hostname: {clean_hostname},
                    username: {settings.SSH_USERNAME}
                    client_key: {settings.SSH_KEY_PATH}                    
                  """)
            
            async with asyncssh.connect(
                clean_hostname,
                username=settings.SSH_USERNAME,
                client_keys=[settings.SSH_KEY_PATH],
                known_hosts=None
            ) as conn:
                command = f"sudo -u {sudo_username} /usr/local/bin/pm2 restart {service_name}"
                logger.info(f"Executing command on {hostname}: {command}")
                result = await conn.run(command)
                if result.exit_status == 0:
                    message = f"""
                    MINER-RESTARTER                     
                    Successfully restarted miner {service_name} on {hostname}"""
                    send_notification_to_all(message)

                    logger.info(
                        f"Successfully restarted {service_name} on {hostname}")
                else:
                    message = f"""
                    MINER-RESTARTER                     
                    Failed to restart miner {service_name} on {hostname}"""
                    send_notification_to_all(message)
                    logger.error(
                        f"Failed to restart {service_name}: {result.stderr}")
        except Exception as e:
            logger.error(f"SSH connection/command failed: {str(e)}")

    async def monitor_and_restart(self, url: str, monitor_name: str):
        logger.info(f"Starting monitoring task for {url} ({monitor_name})")
        
        # Add validation for url parameter
        if not url:
            logger.error(f"URL is None or empty for monitor {monitor_name}")
            return
        
        settings = Settings()
        failures = 0
        checks = 0

        for _ in range(settings.CHECK_COUNT):
            is_healthy = await self.check_endpoint(url, settings.TIMEOUT_THRESHOLD)

            if not is_healthy:
                failures += 1
                logger.info(
                    f"Check failed for {url} ({failures}/{settings.CHECK_COUNT})")
            else:
                logger.info(f"Check passed for {url}")

            if failures < settings.CHECK_COUNT:
                await asyncio.sleep(settings.CHECK_INTERVAL)
            checks += 1

        if failures == settings.CHECK_COUNT:
            logger.info(f"All checks failed for {url}, initiating restart")
            try:
                message = f"""
                MINER-RESTARTER
                After {settings.CHECK_COUNT} checks in {settings.CHECK_INTERVAL} second intervals and {settings.TIMEOUT_THRESHOLD} second timeout the {monitor_name} miner didn't respond.
                Scheduling restart...\n
                """
                send_notification_to_all(message)
            except Exception as e:
                logger.error(f"Failed to send notifications: {str(e)}")
            try:
                # Use the existing extract_hostname method instead of inline parsing
                hostname = self.extract_hostname(url)
                if hostname:
                    await self.restart_service(hostname, monitor_name)
                else:
                    logger.error(f"Could not extract hostname from URL: {url}")
            except Exception as e:
                logger.error(f"Failed to initiate restart: {str(e)}")

        # Cleanup task reference
        if url in self.active_tasks:
            del self.active_tasks[url]