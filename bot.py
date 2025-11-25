# bot.py
import os
import random
import string
import threading
from typing import List

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery

# -------------------
# Health server (Flask)
# -------------------
# Koyeb sets a PORT env var. Default to 8080 for local testing.
PORT = int(os.environ.get("PORT", 8080))

def run_health_server():
    # Import inside function so this file still runs if Flask isn't installed for other environments
    from flask import Flask, jsonify, request

    app = Flask(__name__)

    @app.route("/health", methods=["GET"])
    def health():
        # Return a simple 200 response so Koyeb can mark the instance healthy
        return jsonify({"status": "ok"}), 200

    @app.route("/", methods=["GET"])
    def root():
        return "Bot running", 200

    # Listen on all interfaces so Koyeb can reach it
    app.run(host="0.0.0.0", port=PORT)

# Spawn the health server in a daemon thread before starting the bot
health_thread = threading.Thread(target=run_health_server, daemon=True)
health_thread.start()

# ==========================
#  CONFIG / ENVIRONMENT
# ==========================
BOT_TOKEN = os.environ["BOT_TOKEN"]
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]

REQUIRED_CHANNELS_RAW = os.environ.get("CHANNELS", "")
REQUIRED_CHANNELS: List[str] = [c.strip() for c in REQUIRED_CHANNELS_RAW.split(",") if c.strip()]
MADE_BY = os.environ.get("MADE_BY", "@fe")
DEMO_NOTICE = "⚠️ Demo account (for testing only). These are randomly generated placeholders."

# ==========================
#  INIT BOT
# ==========================
Bot = Client(
    "ff-accounts-bot",
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH,
)


# Utilities (same as before)
def make_force_sub_markup():
    kb = []
    for ch in REQUIRED_CHANNELS:
        if ch.startswith("@"):
            kb.append([InlineKeyboardButton(text=f"Channel {ch}", url=f"https://t.me/{ch.lstrip('@')}")])
        else:
            kb.append([InlineKeyboardButton(text=f"Channel {ch}", callback_data="noop")])
    kb.append([InlineKeyboardButton(text="I Joined ✅", callback_data="check_subs")])
    return InlineKeyboardMarkup(kb)


def make_after_join_markup():
    return InlineKeyboardMarkup([[InlineKeyboardButton(text="Find unused accounts 🔎", callback_data="find_accounts")]])


def make_server_choice_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="India", callback_data="server_india"),
         InlineKeyboardButton(text="Singapore", callback_data="server_sg")]
    ])


def make_show_account_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton(text="Show 1 Account Result", callback_data="show_one")]])


def make_access_gmail_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton(text="Access Gmail To Change Details", callback_data="access_gmail")]])


async def is_member_of_all(client: Client, user_id: int):
    missing = []
    for ch in REQUIRED_CHANNELS:
        try:
            member = await client.get_chat_member(chat_id=ch, user_id=user_id)
            status = member.status
            if status in ("left", "kicked"):
                missing.append(ch)
        except Exception:
            # treat as missing if bot can't check
            missing.append(ch)
    return (len(missing) == 0, missing)


def gen_demo_gmail():
    name_part = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    gmail = f"{name_part}{random.randint(10,999)}@gmail.com"
    pwd_chars = string.ascii_letters + string.digits + "!@#$%&*"
    password = "".join(random.choices(pwd_chars, k=random.randint(8, 14)))
    level = random.randint(1, 90)
    last_login_year = random.randint(2000, 2023)
    return gmail, password, level, last_login_year


# ==========================
#  HANDLERS
# ==========================
@Bot.on_message(filters.private & filters.command("start", prefixes="/"))
async def start_handler(client: Client, message: Message):
    text = (
        "Welcome! Before you can use the bot, you must join our official channels.\n\n"
        f"{MADE_BY}"
    )
    await message.reply_text(
        text=text,
        reply_markup=make_force_sub_markup(),
        disable_web_page_preview=True,
        quote=True,
    )


@Bot.on_callback_query()
async def cb_handler(client: Client, query: CallbackQuery):
    data = query.data or ""
    user_id = query.from_user.id

    if data == "noop":
        await query.answer("Open the channel link above and join, then press 'I Joined'.", show_alert=False)
        return

    if data == "check_subs":
        if not REQUIRED_CHANNELS:
            await query.answer("No channels configured. Proceeding...", show_alert=False)
            await query.message.edit_text(
                "Welcome to our official FF accounts bot.\n\nChoose an option below.",
                reply_markup=make_after_join_markup(),
            )
            return

        ok, missing = await is_member_of_all(client, user_id)
        if ok:
            await query.answer("Thanks for joining 🎉", show_alert=False)
            await query.message.edit_text(
                "Welcome to our official FF accounts bot.\n\nChoose an option below.",
                reply_markup=make_after_join_markup(),
            )
        else:
            missing_text = ", ".join(missing)
            await query.answer("You are not a member of the required channel(s).", show_alert=False)
            await query.message.edit_text(
                "You did not follow our channel(s). Please join the required channels and press 'I Joined' again.\n\n"
                f"Missing: {missing_text}",
                reply_markup=make_force_sub_markup(),
            )
        return

    if data == "find_accounts":
        await query.answer()
        await query.message.edit_text("Select Your Server", reply_markup=make_server_choice_markup())
        return

    if data in ("server_india", "server_sg"):
        server_name = "India" if data == "server_india" else "Singapore"
        await query.answer(f"{server_name} selected")
        await query.message.edit_text(
            "We Found More Unused FF Accounts For You. Click Below To Get.",
            reply_markup=make_show_account_button()
        )
        return

    if data == "show_one":
        await query.answer()
        gmail, password, level, last_login = gen_demo_gmail()
        result_text = (
            f"{DEMO_NOTICE}\n\n"
            f"Gmail: {gmail}\n"
            f"Password: {password}\n"
            f"Level: {level}\n"
            f"Last Login: {last_login}\n\n"
            "Note: These are placeholder/demo accounts generated by the bot."
        )
        await query.message.edit_text(result_text, reply_markup=make_access_gmail_button(), disable_web_page_preview=True)
        return

    if data == "access_gmail":
        await query.answer()
        await query.message.edit_text("We Soon Add This Features.")
        return

    await query.answer()


# ==========================
#  RUN
# ==========================
if __name__ == "__main__":
    print(f"Bot starting... (demo-mode). Health server listening on port {PORT}")
    Bot.run()
