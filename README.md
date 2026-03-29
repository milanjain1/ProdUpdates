# Product Update PDF Distributor

Slack bot that distributes product update PDFs to multiple customer channels, posted under each CS lead's name and avatar.

## How It Works

1. You drop a PDF in the `#product-updates-staging` channel (with an optional message)
2. The bot detects it and cross-posts to every customer channel in `CHANNEL_MAP`
3. Each post appears as the assigned CS lead (custom name + avatar)
4. A delivery receipt is posted to the log channel

## Setup (15 min)

### 1. Create the Slack App

- Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**
- Name it something like `Product Update Bot`

### 2. Add Bot Scopes

Under **OAuth & Permissions → Scopes → Bot Token Scopes**, add:

| Scope | Why |
|---|---|
| `channels:history` | Detect PDF uploads in public channels |
| `groups:history` | Detect PDF uploads in private channels |
| `files:read` | Read uploaded file info |
| `files:write` | Share files to customer channels |
| `chat:write` | Post messages |
| `chat:write.customize` | Post as custom name/avatar |
| `channels:join` | Auto-join public channels if needed |

### 3. Enable Socket Mode (easiest)

- Go to **Basic Information → App-Level Tokens**
- Click **Generate Token**, name it `socket`, add `connections:write` scope
- Copy the `xapp-...` token
- Go to **Socket Mode** → toggle it **on**

### 4. Subscribe to Events

- Go to **Event Subscriptions** → toggle **on**
- Under **Subscribe to bot events**, add: `file_shared`

### 5. Install the App

- Go to **Install App** → **Install to Workspace**
- Copy the `xoxb-...` Bot Token

### 6. Configure the Bot

```bash
cp .env.example .env
# Fill in your tokens and channel IDs
```

Edit `CHANNEL_MAP` in `app.py` with your actual customer channel IDs and CS lead info.

### 7. Invite the Bot

Invite the bot to your staging channel and every customer channel:
```
/invite @Product Update Bot
```

### 8. Run It

**Option A: Deploy to Railway (recommended — no local setup)**

1. Push this folder to a GitHub repo (can be private)
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub Repo**
3. Select the repo
4. Go to your service's **Variables** tab and add:
   - `SLACK_BOT_TOKEN` = your `xoxb-...` token
   - `SLACK_SIGNING_SECRET` = your signing secret
   - `SLACK_APP_TOKEN` = your `xapp-...` token
   - `STAGING_CHANNEL` = your staging channel ID
   - `LOG_CHANNEL` = (optional) your log channel ID
5. Railway auto-detects `railway.toml` and deploys. Done.

Railway's free tier gives you $5/month of usage — more than enough for this bot. It runs 24/7, auto-restarts on crashes, and you can check logs in the dashboard.

**Option B: Run locally**

```bash
pip install -r requirements.txt
python app.py
```

## Usage

1. Go to `#product-updates-staging`
2. Upload the PDF with a message like: "📦 March Product Updates just shipped — here's what's new!"
3. The bot distributes it to all customer channels and confirms when done

## Customizing the Channel Map

The `CHANNEL_MAP` in `app.py` maps customer channel IDs to CS leads:

```python
CHANNEL_MAP = {
    "C04NFI00001": {
        "lead_name": "Sarah Chen",          # Display name in the post
        "lead_icon": "https://..../pic.png", # Avatar URL
    },
}
```

**Finding IDs:**
- **Channel ID:** Right-click channel → View channel details → ID at the bottom
- **User avatar URL:** Open their Slack profile → right-click avatar → Copy image URL

## v2 Ideas

- [ ] Pull channel map from a Google Sheet instead of hardcoding
- [ ] DM each CS lead for an optional custom note before distributing
- [ ] Slash command `/distribute` as an alternative trigger
- [ ] Auto-detect new customer channels via naming convention
