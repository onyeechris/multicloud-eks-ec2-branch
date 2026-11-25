import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

if not SLACK_WEBHOOK_URL:
    raise Exception("SLACK_WEBHOOK_URL not found in environment variables")

def send_slack_message(message: str):
    """
    Send a message to Slack channel using the webhook.
    """
    payload = {"text": message}
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[Slack Error] Failed to send message: {e}")
