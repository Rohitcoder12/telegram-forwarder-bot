# app.py (FINAL DIAGNOSTIC VERSION)
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
logger_user = logging.getLogger('UserBot')

flask_app = Flask(__name__)
@flask_app.route('/')
def health_check(): return "Bot is alive and configurable!", 200
def run_flask():
    port = int(os.environ.get("PORT", 8080))
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
USER_SESSION_STRING = get_env('USER_SESSION_STRING', 'USER_SESSION_STRING not set!')
KOYEB_API_TOKEN = get_env('KOYEB_API_TOKEN', 'KOYEB_API_TOKEN not set!')
KOYEB_SERVICE_ID = get_env('KOYEB_SERVICE_ID', 'KOYEB_SERVICE_ID not set!')
KOYEB_API_URL = f"https://app.koyeb.com/v1/services/{KOYEB_SERVICE_ID}"
KOYEB_HEADERS = {"Authorization": f"Bearer {KOYEB_API_TOKEN}", "Content-Type": "application/json"}

# --- Koyeb Config Management ---
def get_koyeb_config():
    try:
        response = requests.get(KOYEB_API_URL, headers=KOYEB_HEADERS)
        response.raise_for_status()
        service_definition = response.json().get("service", {}).get("definition", {})
        for env_var in service_definition.get("env", []):
            if env_var.get("key") == "FORWARD_CONFIG_JSON":
                return json.loads(env_var.get("value", "{}"))
        return {}
    except Exception as e:
        logger_control.error(f"Failed to get Koyeb config: {e}")
        return None

def update_koyeb_config(new_config_json):
    try:
        get_response = requests.get(KOYEB_API_URL, headers=KOYEB_HEADERS)
        get_response.raise_for_status()
        current_definition = get_response.json().get("service", {}).get("definition", {})
        env_vars = current_definition.get("env", [])
        config_found = False
        for i, env_var in enumerate(env_vars):
            if env_var.get("key") == "FORWARD_CONFIG_JSON":
                env_vars[i]["value"] = json.dumps(new_config_json)
                config_found = True
                break
        if not config_found:
            env_vars.append({"key": "FORWARD_CONFIG_JSON", "value": json.dumps(new_config_json)})
        payload = {"definition": {"env": env_vars}}
        patch_response = requests.patch(KOYEB_API_URL, headers=KOYEB_HEADERS, json=payload)
        patch_response.raise_for_status()
        return True
    except Exception as e:
        logger_control.error(f"Failed to update Koyeb config: {e} - Response: {patch_response.text}")
        return False

# --- Pyrogram Clients ---
control_bot = Client("control_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
user_bot = Client("user_bot_session", session_string=USER_SESSION_STRING, in_memory=True)
admin_filter = filters.user(ADMIN_ID)

# --- Control Bot Commands ---

# NEW DIAGNOSTIC COMMAND - NO ADMIN FILTER
@control_bot.on_message(filters.command("diag"))
async def diag_command(client, message: Message):
    sender_id = message.from_user.id
    sender_id_type = type(sender_id).__name__
    admin_id_from_env = ADMIN_ID
    admin_id_type = type(admin_id_from_env).__name__
    is_match = sender_id == admin_id_from_env

    reply_text = (
        "🔬 **Diagnostic Report** 🔬\n\n"
        f"**Your User ID (from Telegram):**\n`{sender_id}` (Type: `{sender_id_type}`)\n\n"
        f"**Configured ADMIN_ID (from Koyeb):**\n`{admin_id_from_env}` (Type: `{admin_id_type}`)\n\n"
        f"**Do they match?** -> **{is_match}**\n\n"
    )
    if not is_match:
        reply_text += "🔴 **ACTION REQUIRED:** The IDs do not match! Please go to your Koyeb Environment Variables, delete the `ADMIN_ID`, and **manually type** it again to fix any hidden errors."
    else:
        reply_text += "🟢 The IDs match perfectly. The problem is not the ADMIN_ID filter."

    await message.reply_text(reply_text)


@control_bot.on_message(filters.command("start") & admin_filter)
async def start_command(client, message: Message):
    await message.reply_text("👋 **Hybrid Forwarder Bot**\n\nI am online and ready. Use `/add`, `/delete`, and `/list` to manage forwarding rules.")

# (Add your other command handlers like /add, /addsource, etc. here...)

# --- Userbot Handler ---
config_json = os.environ.get("FORWARD_CONFIG_JSON", "{}")
try:
    forward_rules = json.loads(config_json).get("forwards", {})
    source_chats = [src for rule in forward_rules.values() for src in rule.get("sources", [])]
except json.JSONDecodeError:
    source_chats = []

@user_bot.on_message(filters.chat(source_chats) & ~filters.service if source_chats else filters.create(lambda _, __: False))
async def forwarder_handler(client, message: Message):
    for name, rule in forward_rules.items():
        if message.chat.id in rule.get("sources", []):
            await message.copy(rule["destination"])
            break

# --- Main Application Start ---
async def main():
    await asyncio.gather(control_bot.start(), user_bot.start())
    me_control = await control_bot.get_me()
    me_user = await user_bot.get_me()
    logger_control.info(f"Control Bot started as {me_control.first_name}")
    logger_user.info(f"UserBot started as {me_user.first_name}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger_control.info("Starting application...")
    asyncio.run(main())