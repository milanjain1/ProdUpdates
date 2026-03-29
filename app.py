"""
Product Update PDF Distributor — v1
====================================
Slack Bolt app that listens for a PDF upload in a staging channel,
then cross-posts it to every customer channel using each CS lead's
name and avatar.

Setup:
  1. Create a Slack app at https://api.slack.com/apps
  2. Add Bot Token Scopes:
       - channels:history, groups:history  (detect uploads)
       - files:read                        (read uploaded files)
       - files:write                       (share files to channels)
       - chat:write                        (post messages)
       - chat:write.customize              (post as custom name/avatar)
  3. Enable Event Subscriptions → subscribe to:
       - file_shared
  4. Install the app to your workspace
  5. Invite the bot to STAGING_CHANNEL and every customer channel
  6. Copy your Bot Token + Signing Secret into .env
  7. Fill in the CHANNEL_MAP below
  8. `pip install slack-bolt python-dotenv`
  9. `python app.py`

For production, deploy behind ngrok (dev) or on Railway / Render / Lambda.
"""

import os
import time
import logging
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────

# The channel where you drop the PDF to trigger distribution
STAGING_CHANNEL = os.environ.get("STAGING_CHANNEL", "C0123STAGING")

# Default message that accompanies the PDF
DEFAULT_MESSAGE = (
    "📦 New product update just shipped — see the attached PDF "
    "for everything that's new this month!"
)

# Map each customer channel to the CS lead who "owns" it.
# The bot will post as this person's name + avatar.
#
# To find channel IDs: right-click channel name → "View channel details" → ID at bottom
# To find user IDs:    click a user's profile → ⋮ → "Copy member ID"
# For avatar URLs:     use the user's Slack profile image URL, or any hosted image
#
CHANNEL_MAP = {
    "NEW_OUTPUT_CHANNEL_ID": {
        "lead_name": "Milan",
        "lead_icon": "https://ca.slack-edge.com/placeholder.png",
    },
}
# Optional: a channel where the bot logs delivery receipts
LOG_CHANNEL = os.environ.get("LOG_CHANNEL", None)  # e.g., "C09LOGCHANNEL"

# ──────────────────────────────────────────────
# APP INIT
# ──────────────────────────────────────────────

# Debug: print available environment variables
print("Available env vars:", [k for k in os.environ.keys() if "SLACK" in k or "STAGING" in k])
print("BOT token found:", "SLACK_BOT_TOKEN" in os.environ)

app = App(
    token=os.environ["SLACK_BOT_TOKEN"],
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────

def is_pdf(file_info: dict) -> bool:
    """Check if the uploaded file is a PDF."""
    return (
        file_info.get("mimetype") == "application/pdf"
        or file_info.get("filetype") == "pdf"
    )


def get_public_file_link(client, file_id: str) -> str | None:
    """Make the file publicly shareable and return its permalink."""
    try:
        result = client.files_sharedPublicURL(file=file_id)
        return result["file"].get("permalink_public")
    except Exception:
        # If public sharing is disabled at the org level, we'll fall back
        # to re-uploading or sharing the internal link
        return None


def distribute_pdf(client, file_info: dict, triggering_message: str | None):
    """Send the PDF to every channel in CHANNEL_MAP."""
    file_id = file_info["id"]
    file_name = file_info.get("name", "Product Update.pdf")
    file_url = file_info.get("url_private_download") or file_info.get("url_private")
    permalink = file_info.get("permalink", "")

    # Use the message from the staging channel post, or fall back to default
    message_text = triggering_message or DEFAULT_MESSAGE

    results = {"success": [], "failed": []}

    for channel_id, lead_info in CHANNEL_MAP.items():
        try:
        

            # Method 1: Share the existing file to the channel
            # (Slack will show the PDF preview inline)
            try:
                client.conversations_join(channel=channel_id)
            except Exception:
                pass  # Already in channel, or it's a private channel we're invited to

            # Post the message as the CS lead
            msg_result = client.chat_postMessage(
                channel=channel_id,
                text=f"{message_text}\n\n📎 <{permalink}|{file_name}>",
                username=lead_info["lead_name"],
                icon_url=lead_info["lead_icon"],
                unfurl_links=False,
            )

            results["success"].append(
                {"channel": channel_id, "lead": lead_info["lead_name"]}
            )
            logger.info(f"✅ Posted to {channel_id} as {lead_info['lead_name']}")

            # Rate limit safety — Slack allows ~1 msg/sec for chat.postMessage
            time.sleep(1.2)

        except Exception as e:
            results["failed"].append({"channel": channel_id, "error": str(e)})
            logger.error(f"❌ Failed to post to {channel_id}: {e}")

    return results


def post_delivery_log(client, results: dict, file_name: str):
    """Post a summary of what was delivered to the log channel."""
    if not LOG_CHANNEL:
        return

    success_lines = [
        f"• #{r['channel']} — posted as {r['lead']}" for r in results["success"]
    ]
    fail_lines = [
        f"• #{r['channel']} — ❌ {r['error']}" for r in results["failed"]
    ]

    summary = (
        f"📋 *Product Update Distribution Log*\n"
        f"File: `{file_name}`\n\n"
        f"*Delivered ({len(results['success'])}/{len(CHANNEL_MAP)}):*\n"
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
    """
    Triggered when any file is shared in a channel the bot is in.
    We only act if it's a PDF in the staging channel.
    """
    file_id = event.get("file_id")
    channel_id = event.get("channel_id")

    # Only respond to uploads in the staging channel
    if channel_id != STAGING_CHANNEL:
        return

    # Fetch full file info
    file_resp = client.files_info(file=file_id)
    file_info = file_resp["file"]

    if not is_pdf(file_info):
        logger.info(f"Ignoring non-PDF file: {file_info.get('name')}")
        return

    logger.info(f"🚀 PDF detected in staging: {file_info.get('name')}")

    # Try to grab the message text that accompanied the upload
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

    # Distribute
    results = distribute_pdf(client, file_info, triggering_message)

    # Log
    post_delivery_log(client, results, file_info.get("name", "unknown"))

    # Confirm in the staging channel
    success_count = len(results["success"])
    fail_count = len(results["failed"])
    say(
        f"✅ *Distribution complete!*\n"
        f"Sent `{file_info.get('name')}` to {success_count} channel(s)."
        + (f"\n⚠️ {fail_count} channel(s) failed — check the log." if fail_count else ""),
        channel=STAGING_CHANNEL,
    )


# Acknowledge other events so Slack doesn't retry
@app.event("message")
def handle_message_events(body, logger):
    pass


# ──────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────

if __name__ == "__main__":
    # Option A: Socket Mode (easiest for dev — no public URL needed)
    # Requires SLACK_APP_TOKEN (xapp-...) with connections:write scope
    if os.environ.get("SLACK_APP_TOKEN"):
        logger.info("Starting in Socket Mode...")
        handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
        handler.start()
    else:
        # Option B: HTTP mode (for production behind a public URL)
        logger.info("Starting in HTTP mode on port 3000...")
        app.start(port=int(os.environ.get("PORT", 3000)))
