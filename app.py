# app.py (Advanced Forwarder: Filters, Reply-Only, Replacements)
import os
import asyncio
import threading
import json
import logging
import re
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import Message

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')
logger = logging.getLogger('AdvancedForwarder')

flask_app = Flask(__name__)
@flask_app.route('/')
def health_check(): return "Advanced Forwarder is alive!", 200
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
CONFIG_JSON = get_env('CONFIG_JSON', 'CONFIG_JSON not set!', required=False)

# --- Configuration Processing ---
try:
    if CONFIG_JSON:
        CONFIG = json.loads(CONFIG_JSON)
        ALL_SOURCE_CHATS = list(set([source for rule in CONFIG.get('rules', []) for source in rule.get('from_chats', [])]))
        logger.info(f"Loaded {len(CONFIG.get('rules', []))} rules. Listening on {len(ALL_SOURCE_CHATS)} unique source chats.")
    else:
        CONFIG = {"rules": []}; ALL_SOURCE_CHATS = []
except Exception as e:
    logger.critical(f"CRITICAL: Invalid JSON in CONFIG_JSON! Error: {e}")
    CONFIG = {"rules": []}; ALL_SOURCE_CHATS = []

# --- Pyrogram Client ---
app = Client("my_userbot", session_string=SESSION_STRING, api_id=int(API_ID), api_hash=API_HASH, in_memory=True)

# --- Main Forwarding Logic ---
@app.on_message(filters.chat(ALL_SOURCE_CHATS) & ~filters.service if ALL_SOURCE_CHATS else filters.create(lambda _, __, ___: False))
async def forwarder_handler(client: Client, message: Message):
    for rule in CONFIG.get('rules', []):
        if message.chat.id in rule.get('from_chats', []):
            
            # --- FILTERING LOGIC ---
            
            # Filter 1: Keyword/Specific Key Filter
            keywords = rule.get('keywords')
            if keywords:
                message_text = (message.text or message.caption or "").lower()
                if not any(keyword.lower() in message_text for keyword in keywords):
                    continue # Skip if no keyword matches

            # Filter 2: Message Type Filter
            allowed_types = rule.get('allowed_types') # e.g., ["text", "photo", "video"]
            if allowed_types:
                msg_type = "unknown"
                if message.text: msg_type = "text"
                elif message.photo: msg_type = "photo"
                elif message.video: msg_type = "video"
                elif message.document: msg_type = "document"
                elif message.audio: msg_type = "audio"
                if msg_type not in allowed_types:
                    continue # Skip if message type is not allowed

            # Filter 3: "Only Reply" Filter for Bots/Users
            # This checks if the message is a reply TO YOU.
            if rule.get('only_reply_to_me', False):
                if not message.reply_to_message or not message.reply_to_message.from_user or not message.reply_to_message.from_user.is_self:
                    continue # Skip if it's not a reply to one of your own messages

            # --- MODIFICATION LOGIC ---
            
            text_to_send = message.text or message.caption or ""
            
            # Replacement Logic (Word, Link, Emoji)
            replacements = rule.get('replacements')
            if replacements and text_to_send:
                for old, new in replacements.items():
                    text_to_send = text_to_send.replace(old, new)

            # --- FORWARDING ---
            
            for dest_chat in rule.get('to_chats', []):
                try:
                    # Using copy() is best for preserving media
                    await message.copy(
                        chat_id=dest_chat,
                        caption=text_to_send
                    )
                    logger.info(f"Forwarded message from {message.chat.id} to {dest_chat}.")
                except Exception as e:
                    logger.error(f"Could not forward to {dest_chat}. Error: {e}")
            
            break # Message handled, stop checking other rules

# --- Main Application Start ---
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("Starting Advanced Forwarder Userbot...")
    app.run()