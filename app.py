# app.py (Final Version with /clearwebhook command)
import os
import asyncio
import threading
import json
import logging
import requests
from flask import Flask
from pyrogram import Client, filters, errors
from pyrogram.types import Message

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')
logger_control = logging.getLogger('ControlBot')

flask_app = Flask(__name__)
@flask_app.route('/')
def health_check(): return "Bot is alive!", 200
def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

# --- Environment Variable Loading ---
def get_env(name, message, cast=str):
    if name in os.environ:
        return cast(os.environ[name])
    logging.critical(message)
    exit(1)

API_ID = get_env('API_ID', 'API_ID not set.', int)
API_HASH = get_env('API_HASH', 'API_HASH not set.')
BOT_TOKEN = get_env('BOT_TOKEN', 'BOT_TOKEN not set.')
ADMIN_ID = get_env('ADMIN_ID', 'ADMIN_ID not set.', int)

control_bot = Client(
    "data/control_bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)
admin_filter = filters.user(ADMIN_ID)

# --- NEW COMMAND TO FORCE WEBHOOK DELETION ---
@control_bot.on_message(filters.command("clearwebhook") & admin_filter)
async def clear_webhook_command(client, message: Message):
    """Programmatically clears the bot's webhook."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url="
    try:
        response = requests.get(url)
        response_json = response.json()
        if response_json.get("ok"):
            await message.reply_text("✅ Success! Webhook has been cleared.\n\nPlease redeploy the bot on Koyeb now for the change to take effect.")
        else:
            await message.reply_text(f"❌ Failed to clear webhook. Telegram API response:\n\n`{response_json}`")
    except Exception as e:
        await message.reply_text(f"An error occurred while trying to clear the webhook: {e}")


@control_bot.on_message(filters.command("start") & admin_filter)
async def start_command(client, message: Message):
    # This command now works because the webhook will be cleared.
    welcome_text = (
        "👋 **Welcome! Your bot is now working.**\n\n"
        "If you just used `/clearwebhook`, please **REDEPLOY** the bot on Koyeb now.\n\n"
        "Otherwise, you can proceed with `/login`."
    )
    await message.reply_text(welcome_text)
    
# --- The rest of your command handlers (/login, /add, etc.) go here ---
# (They are unchanged from the previous complete versions I sent)
# ...

# --- Main Application Start ---
async def main():
    # Before starting, let's check the webhook info one last time
    try:
        webhook_info = await control_bot.get_webhook_info()
        if webhook_info.url:
            logger_control.warning(f"WARNING: A webhook is set: {webhook_info.url}. The bot may not receive updates. Please use /clearwebhook.")
    except Exception as e:
        logger_control.error(f"Could not get webhook info: {e}")

    await control_bot.start()
    logger_control.info("Control Bot started.")
    await asyncio.Event().wait()


if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger_control.info("Starting application...")
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Application stopped.")