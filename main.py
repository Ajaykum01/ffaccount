import os
import threading
import random
import string
import asyncio
import aiohttp
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# ───────────────── MongoDB ───────────────── #
MONGO_URL = os.getenv("MONGO_URL")
client = MongoClient(MONGO_URL)
db = client["telegram_bot"]
config_collection = db["config"]
users_collection = db["users"]
tokens_collection = db["tokens"]  # for verification tokens

ADMINS = [int(i) for i in os.getenv("ADMINS", "2117119246").split()]

# ───────────────── Bot ───────────────── #
Bot = Client(
    "Play-Store-Bot",
    bot_token=os.environ["BOT_TOKEN"],
    api_id=int(os.environ["API_ID"]),
    api_hash=os.environ["API_HASH"]
)

HOW_TO_VERIFY_URL = "https://t.me/kpslinkteam/52"
FORCE_SUB_LINKS = [
    "https://yt.openinapp.co/fatz4",
    "https://yt.openinapp.co/u4hem",
    "https://t.me/+JJdz2hyOVRYyNzE1",
    "https://t.me/+hXaGwny7nVo3NDM9",
]

# ───────────────── AroLinks API ───────────────── #
AROLINKS_API = "7a04b0ba40696303483cd4be8541a1a8d831141f"

# ───────────────── Codes instead of timed links ───────────────── #
def load_codes():
    config = config_collection.find_one({"_id": "codes"}) or {}
    return config.get("codes", [])


def save_codes(codes: list):
    config_collection.update_one({"_id": "codes"}, {"$set": {"codes": codes}}, upsert=True)


def get_current_code():
    codes = load_codes()
    if not codes:
        return None  # no codes left
    code = codes.pop(0)  # take first
    save_codes(codes)
    return code


# ───────────────── Server-specific Gmail pool helpers ───────────────── #
def _load_pool(key: str):
    cfg = config_collection.find_one({"_id": key}) or {}
    return cfg.get("list", [])


def _save_pool(key: str, list_of_emails):
    config_collection.update_one({"_id": key}, {"$set": {"list": list_of_emails}}, upsert=True)


def pop_from_pool(key: str):
    """
    Pop and return the first email from stored list. Returns None if empty.
    """
    lst = _load_pool(key)
    if not lst:
        return None
    email = lst.pop(0)
    _save_pool(key, lst)
    return email


# keys we'll use
POOL_INDIA = "gmails_india"
POOL_SGP = "gmails_singapore"

# ───────────────── Helpers ───────────────── #
def gen_token(n: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return ''.join(random.choices(alphabet, k=n))


async def shorten_with_arolinks(long_url: str) -> str:
    encoded_url = urllib.parse.quote_plus(long_url)
    api_url = f"https://arolinks.com/api?api={AROLINKS_API}&url={encoded_url}&format=text"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=20) as resp:
                text = (await resp.text()).strip()
                if text.startswith("http"):
                    return text
                return ""  # failed
    except Exception:
        return ""


async def build_verify_link(bot: Client, token: str) -> str:
    me = await bot.get_me()
    deep_link = f"https://t.me/{me.username}?start=GL{token}"
    short = await shorten_with_arolinks(deep_link)
    return short or deep_link


def ensure_user(user_id: int):
    # store per-user flags for key flow
    if not users_collection.find_one({"_id": user_id}):
        users_collection.insert_one({
            "_id": user_id,
            "awaiting_key": False,
            "key_verified": False
        })


# ───────────────── Helpers for FF accounts simulation ───────────────── #
def gen_random_password():
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    length = random.randint(8, 14)
    return ''.join(random.choices(chars, k=length))


def gen_random_level():
    return random.randint(1, 90)


def gen_random_last_login_year():
    return random.randint(2000, 2023)


# ───────────────── Handlers ───────────────── #
@Bot.on_message(filters.command("start") & filters.private)
async def start(bot, message):
    user_id = message.from_user.id
    ensure_user(user_id)

    if len(message.command) > 1:
        payload = message.command[1]
        if payload.startswith("GL"):
            token = payload[2:]
            tok = tokens_collection.find_one({"_id": token})
            if not tok:
                return await message.reply("⚠️ Token not found or expired. Tap **Generate Code** again.")

            if tok.get("user_id") != user_id:
                return await message.reply("⚠️ This verification link belongs to another account. Please generate your own.")

            if tok.get("used"):
                return await message.reply("ℹ️ This token is already verified. Tap **Generate Again** to start over.")

            btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("Verify now by clicking me✅", callback_data=f"final_verify:{token}")]
            ])
            return await message.reply(
                "✅ Short link completed!\n\nTap the button below to complete verification.",
                reply_markup=btn
            )

    buttons = [[InlineKeyboardButton("Subscribe Channel 😎", url=url)] for url in FORCE_SUB_LINKS]
    buttons.append([InlineKeyboardButton("Verify ✅", callback_data="verify")])
    await message.reply("**JOIN GIVEN CHANNEL TO GET REDEEM CODE**", reply_markup=InlineKeyboardMarkup(buttons))


# --- Modified flow: verify → joined → admin key → servers ---

@Bot.on_callback_query(filters.regex("^verify$"))
async def verify_channels(bot, query):
    try:
        await query.message.delete()
    except Exception:
        pass

    join_btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("Joined ✅", callback_data="joined")]
    ])
    await bot.send_message(
        query.from_user.id,
        "Click Below Joined To Start.",
        reply_markup=join_btn
    )
    await query.answer()


@Bot.on_callback_query(filters.regex("^joined$"))
async def joined_handler(bot, query):
    """
    After clicked Joined, make the user enter Admin Login Key.
    """
    user_id = query.from_user.id
    ensure_user(user_id)

    try:
        await query.message.delete()
    except Exception:
        pass

    # mark this user as waiting for key, not verified yet
    users_collection.update_one(
        {"_id": user_id},
        {"$set": {"awaiting_key": True, "key_verified": False}}
    )

    await bot.send_message(
        user_id,
        "🔑 *Admin Login Required*\n\n"
        "Please enter the **Admin Login Key** provided by Garena Admin."
    )
    await query.answer("Enter Admin Login Key")


# handle user messages for key input (NO ~filters.command)
@Bot.on_message(filters.private & filters.text)
async def handle_admin_key(bot, message):
    # ignore commands like /start, /keygen etc.
    if message.text.startswith("/"):
        return

    user_id = message.from_user.id
    text = message.text.strip()

    user = users_collection.find_one({"_id": user_id})
    if not user or not user.get("awaiting_key", False):
        # user is not in key step, ignore
        return

    key_doc = config_collection.find_one({"_id": "admin_key"}) or {}
    current_key = key_doc.get("key")

    if not current_key:
        await message.reply("⚠️ No active Admin Login Key right now. Please try again later.")
        return

    if text != current_key:
        # wrong or old key
        await message.reply("Key is expired by Garena Admin.")
        return

    # correct key
    users_collection.update_one(
        {"_id": user_id},
        {"$set": {"awaiting_key": False, "key_verified": True}}
    )

    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("Find Unused Accounts", callback_data="find_accounts")]
    ])

    await message.reply(
        "Welcome to our official FF accounts bot.",
        reply_markup=btn
    )


@Bot.on_callback_query(filters.regex("^find_accounts$"))
async def find_accounts(bot, query):
    try:
        await query.message.delete()
    except Exception:
        pass

    user_id = query.from_user.id
    user = users_collection.find_one({"_id": user_id}) or {}

    # only allow if key verified
    if not user.get("key_verified", False):
        await query.answer("Please enter a valid Admin Login Key first.", show_alert=True)
        return

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("India", callback_data="server:india"),
         InlineKeyboardButton("Singapore", callback_data="server:singapore")]
    ])
    await bot.send_message(
        query.from_user.id,
        "Select Your Server",
        reply_markup=markup
    )
    await query.answer()


@Bot.on_callback_query(filters.regex(r"^server:(.+)$"))
async def server_selected(bot, query):
    server = query.data.split(":", 1)[1]
    try:
        await query.message.delete()
    except Exception:
        pass

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("Show 1 Account Result", callback_data=f"show_account:{server}")]
    ])
    await bot.send_message(
        query.from_user.id,
        "We Found More Unused FF Accounts For You. Click Below To Get.",
        reply_markup=markup
    )
    await query.answer(f"Server: {server}")


@Bot.on_callback_query(filters.regex(r"^show_account:(.+)$"))
async def show_account(bot, query):
    server = query.data.split(":", 1)[1]
    try:
        await query.message.delete()
    except Exception:
        pass

    # pick pool key
    pool_key = POOL_INDIA if server.lower() == "india" else POOL_SGP

    gmail = pop_from_pool(pool_key)
    if gmail is None:
        await bot.send_message(
            query.from_user.id,
            "❌ No Gmail accounts available for this server right now.Try Later\n\n"
        )
        await query.answer("No gmails available", show_alert=True)
        return

    password = gen_random_password()
    level = gen_random_level()
    last_login = gen_random_last_login_year()

    text = (
        "Gmail Account :-\n\n"
        f"Gmail: {gmail}\n"
        f"Password: {password}\n"
        f"Level: {level}\n"
        f"Last Login: {last_login}."
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("Access Gmail To Change Details", callback_data="access_gmail")]
    ])

    await bot.send_message(
        query.from_user.id,
        text,
        reply_markup=markup
    )
    await query.answer("Account shown ✅")


@Bot.on_callback_query(filters.regex("^access_gmail$"))
async def access_gmail(bot, query):
    try:
        await query.message.delete()
    except Exception:
        pass

    await bot.send_message(
        query.from_user.id,
        "We Soon Add This Features."
    )
    await query.answer("Soon ✅")


# ───────────────── Admin commands for per-server Gmail pools ───────────────── #
@Bot.on_message(filters.command("ingmail") & filters.private)
async def set_ingmails(bot, message):
    if message.from_user.id not in ADMINS:
        return await message.reply("You are not authorized to use this command.")
    parts = message.text.split()[1:]
    if not parts:
        return await message.reply("Usage: /ingmail email1 email2 ...")
    emails = [p.strip() for p in parts if "@" in p]
    if not emails:
        return await message.reply("No valid emails found. Include emails separated by space.")
    _save_pool(POOL_INDIA, emails)
    await message.reply(f"✅ India Gmail pool updated. Total {len(emails)} emails set.")


@Bot.on_message(filters.command("sigmail") & filters.private)
async def set_sigmails(bot, message):
    if message.from_user.id not in ADMINS:
        return await message.reply("You are not authorized to use this command.")
    parts = message.text.split()[1:]
    if not parts:
        return await message.reply("Usage: /sigmail email1 email2 ...")
    emails = [p.strip() for p in parts if "@" in p]
    if not emails:
        return await message.reply("No valid emails found. Include emails separated by space.")
    _save_pool(POOL_SGP, emails)
    await message.reply(f"✅ Singapore Gmail pool updated. Total {len(emails)} emails set.")


@Bot.on_message(filters.command("show_ingmail") & filters.private)
async def show_ingmails(bot, message):
    if message.from_user.id not in ADMINS:
        return await message.reply("You are not authorized to use this command.")
    gmails = _load_pool(POOL_INDIA)
    if not gmails:
        return await message.reply("India Gmail pool is empty.")
    text = "India Gmail pool (first shown will be popped on use):\n\n" + "\n".join(gmails)
    await message.reply(text)


@Bot.on_message(filters.command("show_sigmail") & filters.private)
async def show_sigmails(bot, message):
    if message.from_user.id not in ADMINS:
        return await message.reply("You are not authorized to use this command.")
    gmails = _load_pool(POOL_SGP)
    if not gmails:
        return await message.reply("Singapore Gmail pool is empty.")
    text = "Singapore Gmail pool (first shown will be popped on use):\n\n" + "\n".join(gmails)
    await message.reply(text)


@Bot.on_message(filters.command("clear_ingmail") & filters.private)
async def clear_ingmails(bot, message):
    if message.from_user.id not in ADMINS:
        return await message.reply("You are not authorized to use this command.")
    _save_pool(POOL_INDIA, [])
    await message.reply("✅ India Gmail pool cleared.")


@Bot.on_message(filters.command("clear_sigmail") & filters.private)
async def clear_sigmails(bot, message):
    if message.from_user.id not in ADMINS:
        return await message.reply("You are not authorized to use this command.")
    _save_pool(POOL_SGP, [])
    await message.reply("✅ Singapore Gmail pool cleared.")


# ───────────────── Admin Login Key: /keygen ───────────────── #
@Bot.on_message(filters.command("keygen") & filters.private)
async def keygen(bot, message):
    """
    Admin-only.
    /keygen            -> generate random key
    /keygen CUSTOMKEY  -> set custom key

    Only ONE key is stored. New key overwrites old key.
    """
    if message.from_user.id not in ADMINS:
        return await message.reply("You are not authorized to use this command.")

    parts = message.text.split()[1:]
    if parts:
        new_key = parts[0].strip()
    else:
        new_key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

    config_collection.update_one(
        {"_id": "admin_key"},
        {"$set": {"key": new_key, "created_at": datetime.utcnow()}},
        upsert=True
    )

    await message.reply(
        "✅ New Admin Login Key generated.\n\n"
        f"`{new_key}`\n\n"
        "Old key is expired by Garena Admin."
    )


# ───────────────── Existing verify/gen_code handlers ───────────────── #
@Bot.on_callback_query(filters.regex("^gen_code$"))
async def generate_code(bot, query):
    user_id = query.from_user.id
    ensure_user(user_id)

    token = gen_token()
    tokens_collection.insert_one({
        "_id": token,
        "user_id": user_id,
        "used": False,
        "created_at": datetime.utcnow()
    })

    verify_url = await build_verify_link(bot, token)

    caption = (
        "🔐 **Verification Required**\n\n"
        "1) Tap **Verify (Click me)** and complete the steps.\n"
        "2) When you press **Get Link** there, you'll return here automatically.\n"
        "3) Then you'll get a button **“Verify now by clicking me✅”**."
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("Verify 🙂", url=verify_url)],
        [InlineKeyboardButton("How to verify ❓", url=HOW_TO_VERIFY_URL)],
    ])

    try:
        await query.message.delete()
    except Exception:
        pass

    await bot.send_message(user_id, caption, reply_markup=buttons, disable_web_page_preview=True)
    await query.answer()


@Bot.on_callback_query(filters.regex(r"^final_verify:(.+)$"))
async def final_verify(bot, query):
    user_id = query.from_user.id
    token = query.data.split(":", 1)[1]

    tok = tokens_collection.find_one({"_id": token})
    if not tok:
        return await query.answer("Token not found or expired.", show_alert=True)

    if tok.get("user_id") != user_id:
        return await query.answer("This token belongs to another account.", show_alert=True)

    if tok.get("used"):
        return await query.answer("Token already verified. Use Generate Again.", show_alert=True)

    tokens_collection.update_one({"_id": token}, {"$set": {"used": True, "used_at": datetime.utcnow()}})

    code = get_current_code()
    if not code:
        caption = "❌ No redeem codes available right now. Please try again later."
    else:
        caption = (
            "✅ Verification Successful!\n\n"
            f"🎁 Redeem Code:- {code}\n\n"
            "🔄 You can generate again later."
        )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("Generate Again", callback_data="gen_code")]
    ])

    try:
        await query.message.delete()
    except Exception:
        pass

    await bot.send_message(user_id, caption, reply_markup=buttons, disable_web_page_preview=True)
    await query.answer("Verified ✅")


# ───────────────── Admin ───────────────── #
@Bot.on_message(filters.command("time") & filters.private)
async def set_codes(bot, message):
    if message.from_user.id not in ADMINS:
        return await message.reply("You are not authorized to use this command.")

    try:
        parts = message.text.split()[1:]  # skip "/time"
        if not parts:
            return await message.reply("Usage: /time CODE1 CODE2 CODE3 ...")

        save_codes(parts)
        await message.reply(f"✅ Codes updated successfully!\n\nTotal {len(parts)} codes set.")
    except Exception as e:
        await message.reply(f"Error: {e}")


@Bot.on_message(filters.command("broadcast") & filters.private)
async def broadcast(bot, message):
    if message.from_user.id not in ADMINS:
        return await message.reply("You are not authorized to use this command.")
    if len(message.command) < 2:
        return await message.reply("Usage: /broadcast <your message>")
    broadcast_text = message.text.split(None, 1)[1]
    count = 0
    for user in users_collection.find():
        try:
            await bot.send_message(chat_id=user['_id'], text=broadcast_text)
            count += 1
        except:
            continue
    await message.reply(f"Broadcast sent to {count} users.")


# ───────────────── Health Check ───────────────── #
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is Alive!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()


def run_server():
    server = HTTPServer(("0.0.0.0", 8080), HealthCheckHandler)
    server.serve_forever()


# ───────────────── Main ───────────────── #
if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    Bot.run()
