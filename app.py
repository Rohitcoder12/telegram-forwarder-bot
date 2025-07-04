# app.py (Simple Forwarder - Based on the working "Bare Minimum" test)
import os
import asyncio
import threading
import json
import logging
from flask import Flask
from pyrogram import Client, filters

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')
logger = logging.getLogger('SimpleForwarder')

flask_app = Flask(__name__)
@flask_app.route('/')
def health_check(): return "Simple Forwarder is alive!", 200
def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

# --- Environment Variable Loading ---
def get_env(name, message, required=True):
    val = os.environ.get(name)
    if val: return val
    if required: logging.critical(message); exit(1)
    return None

API_ID = get_env('API_ID', 'API_ID not set!')
API_HASH = get_env('API_HASH', 'API_HASH not set!')
SESSION_STRING = get_env('SESSION_STRING', 'SESSION_STRING not set!')
FROM_CHATS_STR = get_env('FROM_CHATS', 'FROM_CHATS not set!')
TO_CHATS_STR = get_env('TO_CHATS', 'TO_CHATS not set!')

# --- Process Environment Variables ---
try:
    # Convert space-separated strings of IDs into lists of integers
    FROM_CHATS = [int(i) for i in FROM_CHATS_STR.split()]
    TO_CHATS = [int(i) for i in TO_CHATS_STR.split()]
except ValueError:
    logger.critical("FROM_CHATS and TO_CHATS must be space-separated lists of numbers.")
    exit()

# --- Pyrogram Client ---
# We use in_memory=True to avoid any file system errors.
app = Client("my_userbot", session_string=SESSION_STRING, api_id=int(API_ID), api_hash=API_HASH, in_memory=True)

# --- The Forwarding Handler ---
@app.on_message(filters.chat(FROM_CHATS) & ~filters.service)
async def forward_handler(client: Client, message):
    logger.info(f"Detected message from source: {message.chat.id}. Forwarding...")
    for chat_id in TO_CHATS:
        try:
            await message.copy(chat_id)
        except Exception as e:
            logger.error(f"Could not forward to {chat_id}. Error: {e}")
    logger.info("Forwarding complete for this message.")

# --- Main Application Start ---
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("Starting Simple Forwarder Userbot...")
    app.run()