# app.py (CORRECTED "Super-Forwarder": No Bot Token Needed)
import os
import asyncio
import threading
import json
import logging
import re
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import Message, MessageEntity

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')
logger = logging.getLogger('SuperForwarder')

flask_app = Flask(__name__)
@flask_app.route('/')
def health_check(): return "Super-Forwarder is alive!", 200
def run_flask():
    port = int(os.environ.get("PORT", 10000))
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
CONFIG_JSON = get_env('CONFIG_JSON', 'CONFIG_JSON not set!')

# --- Configuration Processing ---
try:
    CONFIG = json.loads(CONFIG_JSON)
    ALL_SOURCE_CHATS = list(set([source for rule in CONFIG.get('rules', []) for source in rule.get('from_chats', [])]))
    logger.info(f"Loaded {len(CONFIG.get('rules', []))} rules. Listening on {len(ALL_SOURCE_CHATS)} unique source chats.")
except (json.JSONDecodeError, KeyError) as e:
    logger.critical(f"CRITICAL: Invalid JSON in CONFIG_JSON environment variable! Error: {e}")
    CONFIG = {"rules": []}
    ALL_SOURCE_CHATS = []

# --- Pyrogram Client ---
app = Client("my_userbot", session_string=SESSION_STRING, api_id=int(API_ID), api_hash=API_HASH, in_memory=True)

# --- Main Forwarding Logic ---
@app.on_message(filters.chat(ALL_SOURCE_CHATS) & ~filters.service if ALL_SOURCE_CHATS else filters.create(lambda _, __: False))
async def forwarder_handler(client: Client, message: Message):
    for rule in CONFIG.get('rules', []):
        if message.chat.id in rule.get('from_chats', []):
            keywords = rule.get('keywords')
            if keywords:
                message_text = (message.text or message.caption or "").lower()
                if not any(keyword.lower() in message_text for keyword in keywords):
                    continue

            original_text = message.text or message.caption
            text_to_send = original_text
            entities_to_send = message.entities or message.caption_entities
            
            replacements = rule.get('replacements')
            if replacements and text_to_send:
                for old, new in replacements.items():
                    text_to_send = text_to_send.replace(old, new)
                
                if text_to_send != original_text:
                    entities_to_send = None # Clear entities if text is modified

            for dest_chat in rule.get('to_chats', []):
                try:
                    # Using copy() is generally better as it preserves media and some formatting
                    await message.copy(
                        chat_id=dest_chat,
                        caption=text_to_send if text_to_send != original_text else None
                    )
                    logger.info(f"Forwarded message from {message.chat.id} to {dest_chat}.")
                except Exception as e:
                    logger.error(f"Could not forward to {dest_chat}. Error: {e}")
            break

# --- Main Application Start ---
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("Starting Super-Forwarder Userbot...")
    app.run()