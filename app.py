# app.py (Simple Config Forwarder)
import os
import asyncio
import threading
import logging
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import Message

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')
logger = logging.getLogger('SimpleConfigForwarder')

flask_app = Flask(__name__)
@flask_app.route('/')
def health_check(): return "Simple Config Forwarder is alive!", 200
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
FORWARD_MAP_STR = get_env('FORWARD_MAP', 'FORWARD_MAP not set!', required=False)

# --- New Configuration Parser ---
def parse_forward_map(map_string):
    """
    Parses the simple "source -> destination" format.
    Example: "-1001 -1002 -> -1003 ; -1004 -> -1005"
    """
    rules = []
    all_source_chats = set()
    if not map_string:
        return rules, []

    # Split the entire string into individual rule strings by the semicolon
    rule_strings = [rule.strip() for rule in map_string.split(';') if rule.strip()]
    
    for i, rule_str in enumerate(rule_strings):
        if '->' not in rule_str:
            logger.warning(f"Skipping invalid rule format (missing '->'): {rule_str}")
            continue
            
        source_part, dest_part = rule_str.split('->', 1)
        
        try:
            # Get sources, split by space, convert to int
            from_chats = [int(s.strip()) for s in source_part.strip().split()]
            # Get destinations, split by space, convert to int
            to_chats = [int(d.strip()) for d in dest_part.strip().split()]
            
            if not from_chats or not to_chats:
                logger.warning(f"Skipping rule with empty sources or destinations: {rule_str}")
                continue

            rule = {
                "name": f"rule_{i+1}", # Auto-generate a name
                "from_chats": from_chats,
                "to_chats": to_chats
            }
            rules.append(rule)
            all_source_chats.update(from_chats)
            
        except ValueError:
            logger.error(f"Could not parse rule due to invalid number: {rule_str}")
            continue
            
    return rules, list(all_source_chats)

# --- Process Configuration ---
FORWARDING_RULES, ALL_SOURCE_CHATS = parse_forward_map(FORWARD_MAP_STR)
if FORWARDING_RULES:
    logger.info(f"Loaded {len(FORWARDING_RULES)} forwarding rules. Listening on {len(ALL_SOURCE_CHATS)} unique chats.")
else:
    logger.warning("No valid forwarding rules found in FORWARD_MAP. The bot will start but will not forward anything.")

# --- Pyrogram Client ---
app = Client("my_userbot", session_string=SESSION_STRING, api_id=int(API_ID), api_hash=API_HASH, in_memory=True)

# --- Main Forwarding Logic ---
@app.on_message(filters.chat(ALL_SOURCE_CHATS) & ~filters.service if ALL_SOURCE_CHATS else filters.create(lambda _, __, ___: False))
async def forwarder_handler(client: Client, message: Message):
    for rule in FORWARDING_RULES:
        if message.chat.id in rule["from_chats"]:
            # This message matches a rule, forward it to all destinations of that rule
            for dest_chat in rule["to_chats"]:
                try:
                    await message.copy(dest_chat)
                except Exception as e:
                    logger.error(f"Could not forward to {dest_chat}. Error: {e}")
            
            # Once a matching rule is found and processed, stop checking other rules
            break

# --- Main Application Start ---
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("Starting Simple Config Forwarder...")
    app.run()