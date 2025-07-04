# Super-Forwarder Telegram Bot

This is a powerful, "headless" Telegram userbot designed to automatically forward messages from multiple source chats to multiple destination chats with advanced filtering and modification capabilities. It is built using Python and Pyrogram and is designed for easy deployment on free cloud platforms like Koyeb or Render.

The bot is configured entirely through environment variables, making it secure and easy to manage without changing any code.

## Features

-   **Multi-Rule Forwarding:** Set up an unlimited number of independent forwarding rules (e.g., A -> B, C -> D).
-   **Multi-Source/Destination:** Each rule can have multiple source chats and multiple destination chats.
-   **All Chat Types Supported:** Forward from public/private channels, groups, bots, or direct messages.
-   **Keyword Filtering:** Only forward messages that contain specific keywords.
-   **Link Replacement:** Automatically replace specified links in a message with your own links before forwarding.
-   **Bypass Restrictions:** Uses a user account (via a session string) to access content in restricted channels and bypass "forwarding not allowed" limitations.
-   **Stateless and Cloud-Ready:** Runs perfectly on free-tier services like Koyeb and Render without needing a persistent disk.

---

## Deployment Instructions

This bot is designed for cloud deployment. Using a service like [Koyeb](https://www.koyeb.com/) or [Render](https://render.com/) is recommended.

### Step 1: Get Your Credentials

You will need the following information before you start:

1.  **Telegram `API_ID` and `API_HASH`**:
    -   Go to [my.telegram.org](https://my.telegram.org).
    -   Log in with your Telegram account.
    -   Go to "API development tools" and create a new app.
    -   Copy the `api_id` and `api_hash`.

2.  **Pyrogram `SESSION_STRING`**:
    -   Since the bot needs to log in as you, it requires a session string.
    -   The safest way to generate this is using a public tool like the **[Replit Session Generator](https://replit.com/@telegram_session/pyrogram)**. This is a **one-time process**.
    -   Follow the on-screen instructions to enter your API credentials and phone number. The script will output a long session string. **Copy this entire string and keep it safe.**

### Step 2: Deploy to Koyeb (or Render)

1.  **Fork this Repository:** Create a fork of this repository into your own GitHub account.
2.  **Create a New App:**
    -   On Koyeb or Render, create a new "Web Service".
    -   Connect your GitHub account and select the repository you just forked.
3.  **Configure the Service:**
    -   The platform should automatically detect it's a Python app.
    -   **Build Command:** `pip install -r requirements.txt`
    -   **Start Command:** `python app.py`

### Step 3: Configure Environment Variables

This is the most important step. The entire bot is controlled by these variables. You need to set these on your hosting platform (e.g., Koyeb).

| Variable Name     | Required? | Description                                                                                                                                                                                            |
| ----------------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `API_ID`          | **Yes**   | Your Telegram API ID from my.telegram.org.                                                                                                                                                             |
| `API_HASH`        | **Yes**   | Your Telegram API Hash from my.telegram.org.                                                                                                                                                             |
| `SESSION_STRING`  | **Yes**   | The long Pyrogram session string you generated. **Set this as a Secret.**                                                                                                                                |
| `CONFIG_JSON`     | **Yes**   | A JSON string containing all your forwarding rules. This is the main configuration for the bot. See examples below.                                                                                      |

---

## `CONFIG_JSON` Examples

All your forwarding logic is defined here. The basic structure is a JSON object with a key `"rules"`, which contains a list of rule objects.

### Example 1: Simple Forwarding

**Goal:** Forward all messages from a source channel (`-100111...`) to a destination channel (`-100222...`).

```json
{
  "rules": [
    {
      "from_chats": [-1001111111111],
      "to_chats": [-1002222222222]
    }
  ]
}
```

### Example 2: Multiple Sources and Destinations

**Goal:** Forward messages from a source channel (`-100111`) AND a source group (`-100333`) to BOTH a destination channel (`-100222`) and a destination group (`-100444`).

```json
{
  "rules": [
    {
      "from_chats": [-100111, -100333],
      "to_chats": [-100222, -100444]
    }
  ]
}
```

### Example 3: Two Separate Forwarding Tasks

**Goal:**
1.  Forward from Channel A to Channel B.
2.  Forward from Group C to Group D.

```json
{
  "rules": [
    {
      "from_chats": [-100111],
      "to_chats": [-100222]
    },
    {
      "from_chats": [-100333],
      "to_chats": [-100444]
    }
  ]
}
```

### Example 4: Keyword Filtering

**Goal:** Forward from a news channel (`-100111`) to your personal channel (`-100222`) **only if** the message contains the word "Breaking" or "Update". The keyword check is case-insensitive.

```json
{
  "rules": [
    {
      "from_chats": [-100111],
      "to_chats": [-100222],
      "keywords": ["Breaking", "Update"]
    }
  ]
}
```

### Example 5: Link Replacement

**Goal:** Forward from a deals channel (`-100111`) to your affiliate channel (`-100222`), and replace their links with yours.

```json
{
  "rules": [
    {
      "from_chats": [-100111],
      "to_chats": [-100222],
      "replacements": {
        "https://original.com/product1": "https://myaffiliate.com/product1",
        "t.me/anothergroup": "t.me/mygroup"
      }
    }
  ]
}
```

### Example 6: The Ultimate Rule (All Features)

**Goal:** Forward from a deals channel (`-100111`) to your affiliate channel (`-100222`) **only if** the message contains "Discount", and also replace the link.

```json
{
  "rules": [
    {
      "from_chats": [-100111],
      "to_chats": [-100222],
      "keywords": ["Discount"],
      "replacements": {
        "t.me/oldgroup": "t.me/mynewgroup"
      }
    }
  ]
}
```

To update your rules, simply edit the `CONFIG_JSON` environment variable on your hosting platform and redeploy the bot.