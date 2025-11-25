# bot.py
import os
import random
import string
from typing import List

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    CallbackQuery,
)

# ==========================
#  CONFIG / ENVIRONMENT
# ==========================
BOT_TOKEN = os.environ["BOT_TOKEN"]
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]

# Channels required for forced-subscribe.
# Provide as comma-separated chat usernames or numeric IDs in environment (no spaces).
# Example: "@channel1,@channel2" or "-1001234567890,@channel2"
REQUIRED_CHANNELS_RAW = os.environ.get("CHANNELS", "")
REQUIRED_CHANNELS: List[str] = [c.strip() for c in REQUIRED_CHANNELS_RAW.split(",") if c.strip()]

# Friendly name used in messages
MADE_BY = os.environ.get("MADE_BY", "@fe")

# Flag: mark results clearly as demo (to avoid misuse)
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


# Utilities
def make_force_sub_markup():
    """Make inline keyboard with channel links + I Joined button"""
    kb = []
    # Show channel link buttons (open links)
    for ch in REQUIRED_CHANNELS:
        # If it's a @username, link to t.me/username; if it's numeric id we can't form a t.me link reliably
        if ch.startswith("@"):
            kb.append([InlineKeyboardButton(text=f"Channel {ch}", url=f"https://t.me/{ch.lstrip('@')}")])
        else:
            # show as text button (user may still click I Joined)
            kb.append([InlineKeyboardButton(text=f"Channel {ch}", callback_data="noop")])
    # I Joined button
    kb.append([InlineKeyboardButton(text="I Joined ✅", callback_data="check_subs")])
    return InlineKeyboardMarkup(kb)


def make_after_join_markup():
    kb = [
        [InlineKeyboardButton(text="Find unused accounts 🔎", callback_data="find_accounts")],
    ]
    return InlineKeyboardMarkup(kb)


def make_server_choice_markup():
    kb = [
        [InlineKeyboardButton(text="India", callback_data="server_india"),
         InlineKeyboardButton(text="Singapore", callback_data="server_sg")],
    ]
    return InlineKeyboardMarkup(kb)


def make_show_account_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton(text="Show 1 Account Result", callback_data="show_one")]])


def make_access_gmail_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton(text="Access Gmail To Change Details", callback_data="access_gmail")]])


async def is_member_of_all(client: Client, user_id: int) -> (bool, List[str]):
    """Check membership for each REQUIRED_CHANNEL. Return (True/False, missing_list)."""
    missing = []
    for ch in REQUIRED_CHANNELS:
        try:
            member = await client.get_chat_member(chat_id=ch, user_id=user_id)
            status = member.status  # 'creator', 'administrator', 'member', 'restricted', 'left', 'kicked'
            if status in ("left", "kicked"):
                missing.append(ch)
        except Exception as e:
            # If get_chat_member fails (e.g., bot not in channel or chat not found), treat as missing
            missing.append(ch)
    return (len(missing) == 0, missing)


def gen_demo_gmail():
    """Generate a dummy gmail and password (clear it's a demo)."""
    name_part = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    gmail = f"{name_part}{random.randint(10,999)}@gmail.com"
    # Generate password with letters + digits + symbols
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
    """When user sends /start in private chat, always show forced-subscribe message."""
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

    # NO-OP (used for channel text buttons that link can't be formed)
    if data == "noop":
        await query.answer("Open the channel link above and join, then press 'I Joined'.", show_alert=False)
        return

    # Check subscriptions
    if data == "check_subs":
        if not REQUIRED_CHANNELS:
            # If no channels configured, allow pass-through
            await query.answer("No channels are configured on this bot. Proceeding...", show_alert=False)
            await query.message.edit_text(
                "Welcome to our official FF accounts bot.\n\nChoose an option below.",
                reply_markup=make_after_join_markup(),
            )
            return

        ok, missing = await is_member_of_all(client, user_id)
        if ok:
            # success
            await query.answer("Thanks for joining 🎉", show_alert=False)
            await query.message.edit_text(
                "Welcome to our official FF accounts bot.\n\nChoose an option below.",
                reply_markup=make_after_join_markup(),
            )
        else:
            # failure - show which channels missing (short)
            missing_text = ", ".join(missing)
            await query.answer("You are not a member of the required channel(s).", show_alert=False)
            await query.message.edit_text(
                "You did not follow our channel(s). Please join the required channels and press 'I Joined' again.\n\n"
                f"Missing: {missing_text}",
                reply_markup=make_force_sub_markup(),
            )
        return

    # After join -> Find unused accounts
    if data == "find_accounts":
        await query.answer()
        await query.message.edit_text(
            "Select Your Server",
            reply_markup=make_server_choice_markup()
        )
        return

    # Server selections
    if data in ("server_india", "server_sg"):
        # optionally store which server the user picked (not persisted in this demo)
        server_name = "India" if data == "server_india" else "Singapore"
        await query.answer(f"{server_name} selected")
        await query.message.edit_text(
            "We Found More Unused FF Accounts For You. Click Below To Get.",
            reply_markup=make_show_account_button()
        )
        return

    # Show one account
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
        await query.message.edit_text(
            result_text,
            reply_markup=make_access_gmail_button(),
            disable_web_page_preview=True,
        )
        return

    # Access Gmail button
    if data == "access_gmail":
        await query.answer()
        await query.message.edit_text("We Soon Add This Features.")
        return

    # Fallback
    await query.answer()


# ==========================
#  RUN
# ==========================
if __name__ == "__main__":
    print("Bot starting... (demo-mode: does NOT provide real credentials)")
    Bot.run()
