# userbot.py
import os
import asyncio
import json
import logging
from pyrogram import Client, filters
from pyrogram.errors import FloodWait

# --- Basic Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [Userbot] - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration Management ---
CONFIG_FILE_PATH = "data/config.json"

def get_env(name, message, cast=str):
    if name in os.environ:
        return cast(os.environ[name])
    logger.error(message)
    exit(1)

def load_config():
    if os.path.exists(CONFIG_FILE_PATH):
        with open(CONFIG_FILE_PATH, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {} # Return empty config if file is empty or malformed
    return {}

# --- Pyrogram Userbot Setup ---
API_ID = get_env('API_ID', 'Error: API_ID not found.', int)
API_HASH = get_env('API_HASH', 'Error: API_HASH not found.')

app = Client("data/my_forwarder_session", api_id=API_ID, api_hash=API_HASH)

# --- Core Forwarding Logic ---
@app.on_message(filters.private | filters.group)
async def main_forwarder(client: Client, message):
    # Load the latest config on every message to get real-time updates
    config_cache = load_config()
    if not config_cache:
        return # Do nothing if no config exists

    chat_id = message.chat.id
    
    for name, config in config_cache.items():
        if chat_id in config.get("sources", []):
            destination = config.get("destination")
            if not destination:
                continue

            logger.info(f"Forwarding from source {chat_id} to {destination} (Rule: {name})")
            try:
                await message.copy(destination)
            except FloodWait as e:
                logger.warning(f"FloodWait: Waiting for {e.x} seconds.")
                await asyncio.sleep(e.x)
                await message.copy(destination) # Retry
            except Exception as e:
                logger.error(f"Could not forward message: {e}")
            break # Stop after first match

# --- Main Execution ---
async def run_userbot():
    logger.info("Starting the Userbot (Forwarder)...")
    await app.start()
    logger.info("Userbot is running and forwarding messages.")
    await asyncio.Event().wait()

if __name__ == "__main__":
    if not os.path.exists('data'):
        os.makedirs('data')
    
    try:
        asyncio.run(run_userbot())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Userbot stopped.")