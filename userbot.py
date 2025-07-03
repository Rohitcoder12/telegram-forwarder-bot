# userbot.py
import os
import asyncio
import json
import logging
from pyrogram import Client, filters
from pyrogram.errors import FloodWait

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [Userbot] - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CONFIG_FILE_PATH = "data/config.json"

def load_config():
    if os.path.exists(CONFIG_FILE_PATH):
        with open(CONFIG_FILE_PATH, 'r') as f:
            try: return json.load(f)
            except json.JSONDecodeError: return {}
    return {}

async def main():
    logger.info("Userbot worker started. Waiting for session string in config...")
    
    user_client = None

    while True:
        await asyncio.sleep(5) # Check for config changes every 5 seconds
        config = load_config()
        session_string = config.get("user_session_string")

        if session_string:
            if not user_client:
                # If there's a session string and client is not running, start it
                logger.info("Session string found. Initializing user client...")
                user_client = Client("user_forwarder_session", session_string=session_string)
                try:
                    await user_client.start()
                    me = await user_client.get_me()
                    logger.info(f"User client logged in as {me.first_name} (@{me.username})")
                except Exception as e:
                    logger.error(f"Failed to start user client: {e}")
                    user_client = None # Reset on failure
                    continue
            
            # This is where you would place your forwarding logic
            # For simplicity, we define it right here
            @user_client.on_message(filters.private | filters.group, group=1)
            async def forwarder_logic(client, message):
                # Always load the latest config to get new rules instantly
                current_config = load_config()
                forwards = current_config.get("forwards", {})
                chat_id = message.chat.id
                
                for name, rule in forwards.items():
                    if chat_id in rule.get("sources", []):
                        destination = rule.get("destination")
                        if not destination: continue
                        
                        logger.info(f"Forwarding from {chat_id} to {destination} (Rule: {name})")
                        try:
                            await message.copy(destination)
                        except FloodWait as e:
                            logger.warning(f"FloodWait: Waiting {e.x}s")
                            await asyncio.sleep(e.x)
                            await message.copy(destination)
                        except Exception as e:
                            logger.error(f"Forwarding failed: {e}")
                        break

        elif not session_string and user_client:
            # If session string is removed (logout) and client is running, stop it
            logger.info("Session string removed. Logging out and stopping user client...")
            await user_client.stop()
            user_client = None
            logger.info("User client stopped.")

if __name__ == "__main__":
    if not os.path.exists('data'): os.makedirs('data')
    asyncio.run(main())