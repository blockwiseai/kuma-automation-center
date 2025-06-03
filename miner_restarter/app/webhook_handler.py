import requests
import logging

# Set up logging
log_file = "/root/webhook_handler.log"
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

#axiom token 
#xaat-8f7585cd-f6b0-49c2-9458-3394cb422b6e
#client = axiom_py.Client()
#
#client.ingest_events(
#    dataset="DATASET_NAME",
#    events=[
#    {"event_source": "miner_restarter",
#      "event_data": 
#        {"hotkey_name": "6xx00",
#           "foo" : "bar"},
#       
#       "event_name": "miner_restarted"

#   }

#client.query(r"['s6'] | where foo == 'bar' | limit 100")

# Get the Discord webhook URL from the environment variable
discord_cryptofred_webhook_url = "https://discord.com/api/webhooks/1309535947343528018/bSGldP6QKob2DDOYRwGax0g2SyWyYh0pD8JsvGadPtOgW08-PidPk8BkWn-16kTJKzjF"
discord_error_webhook_url = "https://discord.com/api/webhooks/1297939354303467613/5M_VGMjAGMD2csMezVcP--W7z8Q4L2_sAePti7B9iKGyz5irs1p9LgvxLFPVRg9AW6E0"



def send_discord_error_notification(message):
    send_discord_notification(message, discord_error_webhook_url)
    send_slack_notification(message)


# Function to send a notification to Discord
def send_discord_notification(message, webhook=discord_cryptofred_webhook_url):
    if webhook is None:
        logging.error("Discord webhook URL not set.")
        return    
    data = {"content": f"{message}"}
    response = requests.post(webhook, json=data)
    if response.status_code == 204:
       logging.info("Notification sent to Discord.")
    else:
       logging.error(
           f"""Failed to send Discord notification. Status code: {
               response.status_code}"""
       )

def send_slack_notification(message):
    url = "https://hooks.slack.com/services/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"
    if url is None:
        return
    data = {"text": f"{message}"}    
    requests.post(url, json=data)