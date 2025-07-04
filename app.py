# app.py (FINAL - Render.com File-Based Session Version)
import os
import asyncio
import threading
import json
import logging
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')
logger_control = logging.getLogger('ControlBot')
logger_user = logging.getLogger('UserBot')

# The persistent disk on Render will be mounted at /data
# We will store all our files there.
SESSION_FILE_PATH = "/data/user_forwarder.session"
CONFIG_FILE_PATH = "/data/config.json"

flask_app = Flask(__name__)
@flask_app.route('/')
def health_check(): return "Bot is alive!", 200
def run_flask():
    port = int(os.environ.get("PORT", 10000)) # Render uses PORT 10000
    flask_app.run(host="0.0.0.0", port=port)

# --- Environment Variable Loading ---
def get_env(name, message, required=True, cast=str):
    val = os.environ.get(name)
    if val: return cast(val)
    if required: logging.critical(message); exit(1)
    return None

API_ID = get_env('API_ID', 'API_ID not set!', cast=int)
API_HASH = get_env('API_HASH', 'API_HASH not set!')
BOT_TOKEN = get_env('BOT_TOKEN', 'BOT_TOKEN not set!')
ADMIN_ID = get_env('ADMIN_ID', 'ADMIN_ID not set!', cast=int)

# --- Configuration Management (File-based) ---
def load_config():
    if os.path.exists(CONFIG_FILE_PATH):
        with open(CONFIG_FILE_PATH, 'r') as f:
            try: return json.load(f)
            except json.JSONDecodeError: return {"forwards": {}}
    return {"forwards": {}}

def save_config(config_data):
    with open(CONFIG_FILE_PATH, 'w') as f:
        json.dump(config_data, f, indent=4)

# --- Pyrogram Clients ---
# The control bot can run in memory
control_bot = Client("control_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
# The user bot will use the session file on the persistent disk
user_bot = Client(SESSION_FILE_PATH, api_id=API_ID, api_hash=API_HASH)
admin_filter = filters.user(ADMIN_ID)

# --- Control Bot Commands ---
@control_bot.on_message(filters.command("start") & admin_filter)
async def start_command(client, message):
    await message.reply_text("👋 **Render Forwarder Bot**\n\nI am online. Use `/add`, `/list` to manage rules.")

@control_bot.on_message(filters.command("add") & admin_filter)
async def add_forward(client, message):
    parts = message.text.split()
    if len(parts) != 3: await message.reply_text("<b>Usage:</b> <code>/add <name> <dest_id></code>"); return
    _, name, dest_id_str = parts; dest_id = int(dest_id_str)
    
    config = load_config()
    config["forwards"][name] = {"destination": dest_id, "sources": []}
    save_config(config)
    await message.reply_text(f"✅ Rule '<code>{name}</code>' created. Userbot will apply it on next restart (or instantly if already running).")

# (Add your other command handlers like /addsource, /delete, /list here)

# --- Userbot Handler ---
@user_bot.on_message(~filters.service, group=1)
async def forwarder_handler(client, message):
    config = load_config() # Load the latest rules on every message
    forwards = config.get("forwards", {})
    source_chats = {src for rule in forwards.values() for src in rule["sources"]}
    if message.chat.id in source_chats:
        for name, rule in forwards.items():
            if message.chat.id in rule["sources"]:
                await message.copy(rule["destination"])
                break

# --- Main Application Start ---
async def main():
    await asyncio.gather(
        control_bot.start(),
        user_bot.start() # This will prompt for login in the logs on the first run
    )
    logger_control.info(f"Control Bot started.")
    logger_user.info(f"UserBot started.")
    await asyncio.Event().wait()

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger_control.info("Starting application...")
    asyncio.run(main())