"""
Receives CloudWatch Alarm notifications via SNS and posts to a Slack webhook.
Uses only stdlib — no dependencies to package.
"""

import json
import os
import urllib.request


def lambda_handler(event, context):
    webhook_url = os.environ["SLACK_WEBHOOK_URL"]

    for record in event.get("Records", []):
        try:
            message = json.loads(record["Sns"]["Message"])

            alarm_name = message.get("AlarmName", "Unknown alarm")
            state = message.get("NewStateValue", "UNKNOWN")
            reason = message.get("NewStateReason", "")
            region = message.get("Region", "")

            emoji = "\U0001f534" if state == "ALARM" else "✅"
            env = os.environ.get("ENVIRONMENT", "prod")

            text = (
                f"{emoji} *[{env}] {alarm_name}*\n"
                f"State: {state}\n"
                f"{reason}"
            )
            if region:
                text += f"\nRegion: {region}"

            payload = json.dumps({"payload": text}).encode()
            req = urllib.request.Request(
                webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10)

        except Exception as e:
            print(f"Error processing alarm notification: {e}")
            raise
