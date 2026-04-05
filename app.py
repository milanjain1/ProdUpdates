"""
Product Update PDF Distributor — v2
====================================
Slack Bolt app that listens for a PDF upload in a staging channel,
then cross-posts it to:
  1. Slack customer channels (as a custom name/avatar)
  2. Microsoft Teams channels (via incoming webhooks)
"""

import os
import time
import logging
import json
import urllib.request
import urllib.error
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────

STAGING_CHANNEL = os.environ.get("STAGING_CHANNEL", "C0123STAGING")

DEFAULT_MESSAGE = (
    "New product update just shipped — see the attached PDF "
    "for everything that's new!"
)

# ── SLACK CHANNELS ──
# Map each customer Slack channel to the identity that posts there.
# Bot must be invited to each channel.
CHANNEL_MAP = {
    # "SLACK_CHANNEL_ID": {
    #     "lead_name": "Display Name",
    #     "lead_icon": "https://url-to-avatar.png",
    # },
}

# ── TEAMS CHANNELS ──
# Map a friendly name to the incoming webhook URL for each Teams channel.
# To get a webhook URL: ask the customer's Teams admin to add an
# "Incoming Webhook" connector to the channel and send you the URL.
TEAMS_CHANNELS = {
      "MJ Test 1": "https://default6a68fc6f241a4b2b86bd81627b1344.02.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/cf7e6ca32dff43619ffeec4ef3db1ba6/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=Sqf_eSrbfUMqO603IOOWwEYwvS9tnTAu8SCB9Rp7Zrc",
    # "Customer B": "https://outlook.office.com/webhook/def456...",
}

# Optional: URL to the Augment logo (shown as the avatar in Teams messages)
TEAMS_AVATAR_URL = "https://raw.githubusercontent.com/YOUR_REPO/main/augment-logo.png"

LOG_CHANNEL = os.environ.get("LOG_CHANNEL", None)

# ──────────────────────────────────────────────
# APP INIT
# ──────────────────────────────────────────────

print("Available env vars:", [k for k in os.environ.keys() if "SLACK" in k or "STAGING" in k])
print("BOT token found:", "SLACK_BOT_TOKEN" in os.environ)

app = App(
    token=os.environ["SLACK_BOT_TOKEN"],
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────

def is_pdf(file_info):
    return (
        file_info.get("mimetype") == "application/pdf"
        or file_info.get("filetype") == "pdf"
    )


def distribute_to_slack(client, file_info, message_text):
    """Post the PDF to all Slack customer channels."""
    file_name = file_info.get("name", "Product Update.pdf")
    permalink = file_info.get("permalink", "")
    results = {"success": [], "failed": []}

    for channel_id, lead_info in CHANNEL_MAP.items():
        try:
            if channel_id == STAGING_CHANNEL:
                continue

            try:
                client.conversations_join(channel=channel_id)
            except Exception:
                pass

            client.chat_postMessage(
                channel=channel_id,
                text=f"{message_text}\n\n<{permalink}|{file_name}>",
                username=lead_info["lead_name"],
                icon_url=lead_info["lead_icon"],
                unfurl_links=False,
            )

            results["success"].append(
                {"channel": channel_id, "lead": lead_info["lead_name"], "platform": "slack"}
            )
            logger.info(f"[Slack] Posted to {channel_id} as {lead_info['lead_name']}")
            time.sleep(1.2)

        except Exception as e:
            results["failed"].append({"channel": channel_id, "error": str(e), "platform": "slack"})
            logger.error(f"[Slack] Failed to post to {channel_id}: {e}")

    return results


def distribute_to_teams(file_info, message_text):
    """Post the PDF to all Teams channels via incoming webhooks."""
    file_name = file_info.get("name", "Product Update.pdf")
    permalink = file_info.get("permalink", "")
    results = {"success": [], "failed": []}

    for channel_name, webhook_url in TEAMS_CHANNELS.items():
        try:
            # Teams Adaptive Card with message + PDF link
            card = {
                "type": "message",
                "attachments": [
                    {
                        "contentType": "application/vnd.microsoft.card.adaptive",
                        "content": {
                            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                            "type": "AdaptiveCard",
                            "version": "1.4",
                            "body": [
                                {
                                    "type": "TextBlock",
                                    "text": message_text,
                                    "wrap": True,
                                    "size": "Medium",
                                },
                                {
                                    "type": "TextBlock",
                                    "text": f"[{file_name}]({permalink})",
                                    "wrap": True,
                                    "spacing": "Medium",
                                    "weight": "Bolder",
                                },
                            ],
                        },
                    }
                ],
            }

            data = json.dumps(card).encode("utf-8")
            req = urllib.request.Request(
                webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req)

            results["success"].append(
                {"channel": channel_name, "lead": "Augment", "platform": "teams"}
            )
            logger.info(f"[Teams] Posted to {channel_name}")
            time.sleep(1.0)

        except Exception as e:
            results["failed"].append({"channel": channel_name, "error": str(e), "platform": "teams"})
            logger.error(f"[Teams] Failed to post to {channel_name}: {e}")

    return results


def post_delivery_log(client, results, file_name):
    if not LOG_CHANNEL:
        return

    total_channels = len(CHANNEL_MAP) + len(TEAMS_CHANNELS)

    success_lines = []
    for r in results["success"]:
        platform = r.get("platform", "slack").upper()
        success_lines.append(f"- [{platform}] {r['channel']} posted as {r['lead']}")

    fail_lines = []
    for r in results["failed"]:
        platform = r.get("platform", "slack").upper()
        fail_lines.append(f"- [{platform}] {r['channel']} FAILED: {r['error']}")

    summary = (
        f"*Product Update Distribution Log*\n"
        f"File: `{file_name}`\n\n"
        f"*Delivered ({len(results['success'])}/{total_channels}):*\n"
        + ("\n".join(success_lines) if success_lines else "_None_")
        + "\n\n"
    )
    if fail_lines:
        summary += f"*Failed:*\n" + "\n".join(fail_lines)

    try:
        client.chat_postMessage(channel=LOG_CHANNEL, text=summary)
    except Exception as e:
        logger.error(f"Could not post to log channel: {e}")


# ──────────────────────────────────────────────
# EVENT HANDLER
# ──────────────────────────────────────────────

@app.event("file_shared")
def handle_file_shared(event, client, say):
    file_id = event.get("file_id")
    channel_id = event.get("channel_id")

    if channel_id != STAGING_CHANNEL:
        return

    file_resp = client.files_info(file=file_id)
    file_info = file_resp["file"]

    if not is_pdf(file_info):
        logger.info(f"Ignoring non-PDF file: {file_info.get('name')}")
        return

    logger.info(f"PDF detected in staging: {file_info.get('name')}")

    triggering_message = None
    shares = file_info.get("shares", {})
    public_shares = shares.get("public", {}).get(STAGING_CHANNEL, [])
    private_shares = shares.get("private", {}).get(STAGING_CHANNEL, [])
    all_shares = public_shares + private_shares
    if all_shares:
        ts = all_shares[0].get("ts")
        if ts:
            try:
                history = client.conversations_history(
                    channel=STAGING_CHANNEL, latest=ts, inclusive=True, limit=1
                )
                msgs = history.get("messages", [])
                if msgs and msgs[0].get("text"):
                    triggering_message = msgs[0]["text"]
            except Exception:
                pass

    message_text = triggering_message or DEFAULT_MESSAGE

    # Distribute to both platforms
    slack_results = distribute_to_slack(client, file_info, message_text)
    teams_results = distribute_to_teams(file_info, message_text)

    # Merge results
    all_results = {
        "success": slack_results["success"] + teams_results["success"],
        "failed": slack_results["failed"] + teams_results["failed"],
    }

    post_delivery_log(client, all_results, file_info.get("name", "unknown"))

    success_count = len(all_results["success"])
    fail_count = len(all_results["failed"])

    slack_ok = len(slack_results["success"])
    teams_ok = len(teams_results["success"])

    say(
        f"*Distribution complete!*\n"
        f"Sent `{file_info.get('name')}` to {success_count} channel(s) "
        f"({slack_ok} Slack, {teams_ok} Teams)."
        + (f"\n{fail_count} channel(s) failed — check the log." if fail_count else ""),
        channel=STAGING_CHANNEL,
    )


@app.event("message")
def handle_message_events(body, logger):
    pass


# ──────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────

if __name__ == "__main__":
    if os.environ.get("SLACK_APP_TOKEN"):
        logger.info("Starting in Socket Mode...")
        handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
        handler.start()
    else:
        logger.info("Starting in HTTP mode on port 3000...")
        app.start(port=int(os.environ.get("PORT", 3000)))
