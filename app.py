"""
Product Update PDF Distributor — v1
====================================
Slack Bolt app that listens for a PDF upload in a staging channel,
then cross-posts it to every customer channel using each CS lead's
name and avatar.
"""
 
import os
import time
import logging
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
    "for everything that's new this month!"
)
 
# Replace the channel ID below with your mj-test-output channel ID
CHANNEL_MAP = {
    "C0APYR5741F": {
        "lead_name": "Milan",
        "lead_icon": "https://ca.slack-edge.com/T07S39SPCSG-U0AE6GDPWJU-8f38b0dd5b80-512",
    },
}
 
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
 
 
def distribute_pdf(client, file_info, triggering_message):
    file_id = file_info["id"]
    file_name = file_info.get("name", "Product Update.pdf")
    permalink = file_info.get("permalink", "")
    message_text = triggering_message or DEFAULT_MESSAGE
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
                {"channel": channel_id, "lead": lead_info["lead_name"]}
            )
            logger.info(f"Posted to {channel_id} as {lead_info['lead_name']}")
            time.sleep(1.2)
 
        except Exception as e:
            results["failed"].append({"channel": channel_id, "error": str(e)})
            logger.error(f"Failed to post to {channel_id}: {e}")
 
    return results
 
 
def post_delivery_log(client, results, file_name):
    if not LOG_CHANNEL:
        return
 
    success_lines = [
        f"- #{r['channel']} posted as {r['lead']}" for r in results["success"]
    ]
    fail_lines = [
        f"- #{r['channel']} FAILED: {r['error']}" for r in results["failed"]
    ]
 
    summary = (
        f"*Product Update Distribution Log*\n"
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
 
    results = distribute_pdf(client, file_info, triggering_message)
    post_delivery_log(client, results, file_info.get("name", "unknown"))
 
    success_count = len(results["success"])
    fail_count = len(results["failed"])
    say(
        f"*Distribution complete!*\n"
        f"Sent `{file_info.get('name')}` to {success_count} channel(s)."
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
