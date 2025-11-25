import os
import threading
import random
import string
import asyncio
import aiohttp
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
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

# ───────────────── Constants / Links ───────────────── #
HOW_TO_VERIFY_URL = "https://t.me/kpslinkteam/52"
FORCE_SUB_LINKS = [
    "https://yt.openinapp.co/fatz4",
    "https://yt.openinapp.co/u4hem",
    "https://t.me/+JJdz2hyOVRYyNzE1",
    "https://t.me/+hXaGwny7nVo3NDM9",
]

AROLINKS_API = "7a04b0ba40696303483cd4be8541a1a8d831141f"

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
    if not users_collection.find_one({"_id": user_id}):
        users_collection.insert_one({"_id": user_id})

# Demo account generator (for FF accounts)
def gen_demo_gmail():
    name_part = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    gmail = f"{name_part}{random.randint(10,999)}@gmail.com"
    pwd_chars = string.ascii_letters + string.digits + "!@#$%&*"
    password = "".join(random.choices(pwd_chars, k=random.randint(8, 14)))
    level = random.randint(1, 90)
    last_login_year = random.randint(2000, 2023)
    return gmail, password, level, last_login_year

# ───────────────── Health Check (builtin) ───────────────── #
PORT = int(os.environ.get("PORT", 8080))

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Bot is Alive!")
        else:
            self.send_response(404)
            self.end_headers()

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        return  # silence logs

def run_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthCheckHandler)
    server.serve_forever()

# ───────────────── Bot Flow: Buttons / Keyboards ───────────────── #
def force_sub_buttons():
    buttons = [[InlineKeyboardButton("Subscribe Channel 😎", url=url)] for url in FORCE_SUB_LINKS]
    buttons.append([InlineKeyboardButton("Verify ✅", callback_data="verify")])
    return InlineKeyboardMarkup(buttons)

def after_verify_markup():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Find unused accounts 🔎", callback_data="find_accounts")]])

def server_choice_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("India", callback_data="server_india"),
         InlineKeyboardButton("Singapore", callback_data="server_sg")]
    ])

def show_account_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Show 1 Account Result", callback_data="show_one")]])

def access_gmail_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Access Gmail To Change Details", callback_data="access_gmail")]])

# ───────────────── Handlers ───────────────── #
@Bot.on_message(filters.command("start") & filters.private)
async def start(bot, message):
    user_id = message.from_user.id
    ensure_user(user_id)

    # handle deep-link payload (verification)
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

    # default start message (force subscribe)
    await message.reply("**JOIN GIVEN CHANNEL TO GET REDEEM CODE**", reply_markup=force_sub_buttons())

@Bot.on_callback_query(filters.regex("^verify$"))
async def verify_channels(bot, query):
    try:
        await query.message.delete()
    except Exception:
        pass

    await query.message.reply(
        "🙏 Welcome to NST Free Google Play Redeem Code Bot RS30-200 🪙\nClick **Generate Code** to start verification.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Generate Code", callback_data="gen_code")]])
    )

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

    # --- Instead of giving a redeem code, continue with the FF accounts flow (demo) ---
    try:
        await query.message.delete()
    except Exception:
        pass

    await bot.send_message(
        user_id,
        "Welcome to our official FF accounts bot.\n\nChoose an option below.",
        reply_markup=after_verify_markup()
    )
    await query.answer("Verified ✅")

# ---- New FF account flow handlers ----
@Bot.on_callback_query(filters.regex("^find_accounts$"))
async def cb_find_accounts(bot, query):
    await query.answer()
    await query.message.edit_text("Select Your Server", reply_markup=server_choice_markup())

@Bot.on_callback_query(filters.regex("^server_india$"))
async def cb_server_india(bot, query):
    await query.answer("India selected")
    await query.message.edit_text(
        "We Found More Unused FF Accounts For You. Click Below To Get.",
        reply_markup=show_account_button()
    )

@Bot.on_callback_query(filters.regex("^server_sg$"))
async def cb_server_sg(bot, query):
    await query.answer("Singapore selected")
    await query.message.edit_text(
        "We Found More Unused FF Accounts For You. Click Below To Get.",
        reply_markup=show_account_button()
    )

@Bot.on_callback_query(filters.regex("^show_one$"))
async def cb_show_one(bot, query):
    await query.answer()
    gmail, password, level, last_login = gen_demo_gmail()
    demo_notice = "⚠️ Demo account (for testing only). These are randomly generated placeholders."
    result_text = (
        f"{demo_notice}\n\n"
        f"Gmail: {gmail}\n"
        f"Password: {password}\n"
        f"Level: {level}\n"
        f"Last Login: {last_login}\n\n"
        "Note: These are placeholder/demo accounts generated by the bot."
    )
    await query.message.edit_text(result_text, reply_markup=access_gmail_button(), disable_web_page_preview=True)

@Bot.on_callback_query(filters.regex("^access_gmail$"))
async def cb_access_gmail(bot, query):
    await query.answer()
    await query.message.edit_text("We Soon Add This Features.")

# ───────────────── Admin / Broadcast (kept) ───────────────── #
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

# ───────────────── Main ───────────────── #
if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    print(f"Bot starting... Health server on port {PORT}")
    Bot.run()
