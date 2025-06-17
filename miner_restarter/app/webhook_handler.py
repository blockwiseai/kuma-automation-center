import os
import requests
import logging
from typing import List, Tuple, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set up logging
log_file = "/root/webhook_handler.log"
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def load_webhooks_from_env() -> List[Tuple[str, str]]:
    """
    Load webhook configurations from environment variables.
    Expected format: WEBHOOK_1_TYPE, WEBHOOK_1_URL, WEBHOOK_2_TYPE, WEBHOOK_2_URL, etc.
    """
    webhooks = []
    i = 1
    
    while True:
        webhook_type = os.getenv(f"WEBHOOK_{i}_TYPE")
        webhook_url = os.getenv(f"WEBHOOK_{i}_URL")
        
        if not webhook_type or not webhook_url:
            break
            
        webhooks.append((webhook_type.lower(), webhook_url))
        logging.info(f"Loaded webhook {i}: {webhook_type}")
        i += 1
    
    if not webhooks:
        logging.warning("No webhooks found in environment variables")
    else:
        logging.info(f"Loaded {len(webhooks)} webhooks from environment")
    
    return webhooks


# Load webhooks on module import
WEBHOOKS = load_webhooks_from_env()


def send_notification_to_webhook(webhook_type: str, webhook_url: str, message: str) -> bool:
    """
    Send a notification to a specific webhook based on its type.
    
    Args:
        webhook_type: Type of webhook ('discord' or 'slack')
        webhook_url: The webhook URL
        message: The message to send
    
    Returns:
        bool: True if successful, False otherwise
    """
    if not webhook_url:
        logging.error(f"{webhook_type.capitalize()} webhook URL not provided.")
        return False
    
    try:
        if webhook_type.lower() == "discord":
            data = {"content": message}
            response = requests.post(webhook_url, json=data)
            success = response.status_code == 204
        elif webhook_type.lower() == "slack":
            data = {"text": message}
            response = requests.post(webhook_url, json=data)
            success = response.status_code == 200
        else:
            logging.error(f"Unknown webhook type: {webhook_type}")
            return False
        
        if success:
            logging.info(f"Notification sent to {webhook_type.capitalize()}.")
        else:
            logging.error(
                f"Failed to send {webhook_type.capitalize()} notification. "
                f"Status code: {response.status_code}, Response: {response.text}"
            )
        return success
        
    except Exception as e:
        logging.error(f"Exception sending to {webhook_type}: {str(e)}")
        return False


def send_notification_to_all(message: str, webhooks: Optional[List[Tuple[str, str]]] = None):
    """
    Send a notification to all configured webhooks.
    
    Args:
        message: The message to send
        webhooks: Optional list of (type, url) tuples. If None, uses WEBHOOKS
    """
    if webhooks is None:
        webhooks = WEBHOOKS
    
    if not webhooks:
        logging.warning("No webhooks configured")
        return 0
    
    success_count = 0
    for webhook_type, webhook_url in webhooks:
        if send_notification_to_webhook(webhook_type, webhook_url, message):
            success_count += 1
    
    logging.info(f"Sent notifications to {success_count}/{len(webhooks)} webhooks.")
    return success_count


def send_notification_to_type(message: str, target_type: str, webhooks: Optional[List[Tuple[str, str]]] = None):
    """
    Send a notification to all webhooks of a specific type.
    
    Args:
        message: The message to send
        target_type: The type of webhooks to send to ('discord' or 'slack')
        webhooks: Optional list of (type, url) tuples. If None, uses WEBHOOKS
    """
    if webhooks is None:
        webhooks = WEBHOOKS
    
    filtered_webhooks = [(t, u) for t, u in webhooks if t.lower() == target_type.lower()]
    
    if not filtered_webhooks:
        logging.warning(f"No webhooks found for type: {target_type}")
        return 0
    
    return send_notification_to_all(message, filtered_webhooks)


def reload_webhooks():
    """Reload webhooks from environment variables"""
    global WEBHOOKS
    WEBHOOKS = load_webhooks_from_env()
    return WEBHOOKS


# Example usage:
if __name__ == "__main__":
    # Send to all webhooks
    send_notification_to_all("Test message to all webhooks")
    
    # Send only to Discord webhooks
    send_notification_to_type("Test message to Discord only", "discord")
    
    # Send only to Slack webhooks
    send_notification_to_type("Test message to Slack only", "slack")
    
    # Reload webhooks if environment changed
    reload_webhooks()