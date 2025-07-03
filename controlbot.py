# controlbot.py
import os
import threading
import json
import logging
from flask import Flask
from pyrogram import Client, filters, errors
from pyrogram.types import Message

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [ControlBot] - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

flask_app = Flask(__name__)
@flask_app.route('/')
def health_check(): return "Control Bot is alive!", 200
def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

# --- Config and State Management ---
CONFIG_FILE_PATH = "data/config.json"
# This dictionary will hold the state of the login process for the admin
login_state = {}

def get_env(name, message, cast=str):
    if name in os.environ:
        return cast(os.environ[name])
    logger.error(message)
    exit(1)

def load_config():
    if not os.path.exists(CONFIG_FILE_PATH): return {}
    with open(CONFIG_FILE_PATH, 'r') as f:
        try: return json.load(f)
        except json.JSONDecodeError: return {}

def save_config(config):
    with open(CONFIG_FILE_PATH, 'w') as f:
        json.dump(config, f, indent=4)

# --- Pyrogram Bot Setup ---
API_ID = get_env('API_ID', 'Your API_ID is not set.', int)
API_HASH = get_env('API_HASH', 'Your API_HASH is not set.')
BOT_TOKEN = get_env('BOT_TOKEN', 'Your BOT_TOKEN is not set.')
ADMIN_ID = get_env('ADMIN_ID', 'Your ADMIN_ID is not set.', int)

app = Client("data/control_bot_session", bot_token=BOT_TOKEN)
admin_filter = filters.user(ADMIN_ID)

# --- Login Flow Commands ---
@app.on_message(filters.command("login") & admin_filter)
async def login_start(client, message: Message):
    config = load_config()
    if config.get("user_session_string"):
        await message.reply_text("You are already logged in. Use `/logout` first if you want to switch accounts.")
        return

    login_state[ADMIN_ID] = {"state": "awaiting_phone"}
    await message.reply_text("Please send me the phone number of the account you want to use for forwarding (in international format, e.g., +11234567890).")

@app.on_message(filters.command("logout") & admin_filter)
async def logout(client, message: Message):
    config = load_config()
    if "user_session_string" in config:
        del config["user_session_string"]
        save_config(config)
        await message.reply_text("✅ You have been successfully logged out. The forwarder worker will stop.\nUse `/login` to start again.")
    else:
        await message.reply_text("You are not logged in.")

# --- Main Message Handler for Login ---
@app.on_message(filters.private & admin_filter & ~filters.command())
async def handle_login_steps(client, message: Message):
    if ADMIN_ID not in login_state:
        return # Not in a login process

    state_data = login_state[ADMIN_ID]
    current_state = state_data.get("state")

    if current_state == "awaiting_phone":
        phone = message.text
        # Use an in-memory session for the temporary client
        temp_user_client = Client(":memory:", api_id=API_ID, api_hash=API_HASH)
        try:
            await temp_user_client.connect()
            sent_code = await temp_user_client.send_code(phone)
            state_data["state"] = "awaiting_otp"
            state_data["phone"] = phone
            state_data["phone_code_hash"] = sent_code.phone_code_hash
            await message.reply_text("An OTP has been sent to your Telegram account. Please send it here.")
        except Exception as e:
            await message.reply_text(f"An error occurred: {e}")
            del login_state[ADMIN_ID]
        finally:
            await temp_user_client.disconnect()

    elif current_state == "awaiting_otp":
        otp = message.text
        temp_user_client = Client(":memory:", api_id=API_ID, api_hash=API_HASH)
        try:
            await temp_user_client.connect()
            await temp_user_client.sign_in(state_data["phone"], state_data["phone_code_hash"], otp)
            # On success, export the session string
            session_string = await temp_user_client.export_session_string()
            config = load_config()
            config["user_session_string"] = session_string
            save_config(config)
            await message.reply_text("✅ Login successful! The forwarder worker will now start using this account.\nYou can now use `/add`, `/list`, etc.")
            del login_state[ADMIN_ID]
        except errors.SessionPasswordNeeded:
            state_data["state"] = "awaiting_password"
            await message.reply_text("Your account has Two-Step Verification enabled. Please send your password.")
        except Exception as e:
            await message.reply_text(f"An error occurred: {e}")
            del login_state[ADMIN_ID]
        finally:
            await temp_user_client.disconnect()

    elif current_state == "awaiting_password":
        password = message.text
        temp_user_client = Client(":memory:", api_id=API_ID, api_hash=API_HASH)
        try:
            await temp_user_client.connect()
            # We need to sign in again to check the password
            await temp_user_client.sign_in(state_data["phone"], state_data["phone_code_hash"], "00000") # Bogus OTP
        except errors.SessionPasswordNeeded:
            try:
                await temp_user_client.check_password(password)
                session_string = await temp_user_client.export_session_string()
                config = load_config()
                config["user_session_string"] = session_string
                save_config(config)
                await message.reply_text("✅ Login successful! The forwarder worker will now start.\nYou can now use `/add`, `/list`, etc.")
                del login_state[ADMIN_ID]
            except Exception as e:
                await message.reply_text(f"Password check failed: {e}")
                del login_state[ADMIN_ID]
        finally:
            await temp_user_client.disconnect()

# --- Standard Task Management Commands (add, list, delete) go here ---
# (They are unchanged from the previous version, just copy them here)
# ... (Example /list)
@app.on_message(filters.command("list") & admin_filter)
async def list_forwards(client, message: Message):
    config = load_config()
    if not config.get("forwards"):
        await message.reply_text("No forwarding rules are configured.")
        return
    # ... rest of the list logic ...

# --- Main Execution ---
if __name__ == "__main__":
    if not os.path.exists('data'): os.makedirs('data')
    threading.Thread(target=run_flask, daemon=True).start()
    logger.info("Starting Control Bot...")
    app.run()