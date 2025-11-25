import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv

load_dotenv()

# ----------------------
# Config
# ----------------------
BOT = Client(
    "force-sub-bot",
    bot_token=os.environ["BOT_TOKEN"],
    api_id=int(os.environ["API_ID"]),
    api_hash=os.environ["API_HASH"],
)

# Links shown to users on /start (your original links)
FORCE_SUB_LINKS = [
    "https://yt.openinapp.co/fatz4",
    "https://yt.openinapp.co/u4hem",
    "https://t.me/+JJdz2hyOVRYyNzE1",
    "https://t.me/+hXaGwny7nVo3NDM9",
]

# REQUIRED_CHANNELS must be a comma-separated list of chat identifiers that the bot can check.
# Use @username or numeric chat id (e.g. -1001234567890). Example:
# REQUIRED_CHANNELS=@examplechannel,-1001234567890,@otherchannel
REQUIRED_CHANNELS_RAW = os.environ.get("REQUIRED_CHANNELS", "")
REQUIRED_CHANNELS = [c.strip() for c in REQUIRED_CHANNELS_RAW.split(",") if c.strip()]

HEALTH_PORT = int(os.environ.get("PORT", 8080))


# ----------------------
# Minimal health server
# ----------------------
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        return

def run_health_server():
    server = HTTPServer(("0.0.0.0", HEALTH_PORT), HealthHandler)
    server.serve_forever()

# start health server in background
threading.Thread(target=run_health_server, daemon=True).start()


# ----------------------
# Keyboards
# ----------------------
def start_markup():
    kb = []
    for url in FORCE_SUB_LINKS:
        kb.append([InlineKeyboardButton(text="Open Channel / Link", url=url)])
    kb.append([InlineKeyboardButton(text="I Joined ✅", callback_data="i_joined")])
    return InlineKeyboardMarkup(kb)


# ----------------------
# Helpers
# ----------------------
async def check_membership(client: Client, user_id: int):
    """
    Returns (ok: bool, missing: List[str], unverifiable: List[str])
    - missing: channels the user is not a member of
    - unverifiable: channels that cannot be programmatically verified (e.g. invite links or bot lacks access)
    """
    missing = []
    unverifiable = []

    if not REQUIRED_CHANNELS:
        # If no REQUIRED_CHANNELS configured, we cannot verify automatically.
        return False, [], ["(no REQUIRED_CHANNELS configured)"]

    for ch in REQUIRED_CHANNELS:
        try:
            # If ch looks numeric, convert to int
            chat_id = int(ch) if (ch.lstrip("-").isdigit()) else ch
            member = await client.get_chat_member(chat_id=chat_id, user_id=user_id)
            status = getattr(member, "status", None)
            if status in ("left", "kicked"):
                missing.append(ch)
        except Exception as e:
            # If get_chat_member fails, we can't verify this channel programmatically
            unverifiable.append(ch)

    ok = (len(missing) == 0) and (len(unverifiable) == 0)
    return ok, missing, unverifiable


# ----------------------
# Handlers: only forced-subscribe behavior
# ----------------------
@BOT.on_message(filters.private & filters.command("start", prefixes="/"))
async def on_start(client: Client, message):
    """
    Always show the forced-subscribe message on /start.
    """
    text = (
        "🔒 You must join our required channels before using this bot.\n\n"
        "Open the channels below and press **I Joined** when you're done."
    )
    await message.reply(text, reply_markup=start_markup(), disable_web_page_preview=True, quote=True)


@BOT.on_callback_query(filters.regex("^i_joined$"))
async def on_i_joined(client: Client, query):
    user_id = query.from_user.id

    # Verify membership
    ok, missing, unverifiable = await check_membership(client, user_id)

    if ok:
        # User is a member of all required channels
        await query.answer("Membership verified — you may proceed.", show_alert=True)
        try:
            await query.message.edit_text("✅ Verified — you are a member of all required channels. You can now use the bot.")
        except Exception:
            # fallback to simple reply if edit fails
            await client.send_message(user_id, "✅ Verified — you are a member of all required channels. You can now use the bot.")
        return

    # Not fully verified
    parts = []
    if missing:
        parts.append("You are NOT a member of the following channels:\n" + "\n".join(f"- {c}" for c in missing))
    if unverifiable:
        parts.append(
            "I could NOT automatically verify these channels (bot lacks access or the identifier is an invite link):\n"
            + "\n".join(f"- {c}" for c in unverifiable)
        )
        parts.append(
            "\nTo make verification work, ensure REQUIRED_CHANNELS env var contains public @usernames or numeric chat IDs "
            "and add the bot to private channels."
        )
    reply_text = "⚠️ Verification failed.\n\n" + "\n\n".join(parts)

    await query.answer("Verification failed", show_alert=True)
    try:
        await query.message.edit_text(reply_text, reply_markup=start_markup())
    except Exception:
        await client.send_message(user_id, reply_text, reply_markup=start_markup())


# ----------------------
# Run bot
# ----------------------
if __name__ == "__main__":
    print("Starting force-sub bot (only forced-subscribe behavior).")
    print("REQUIRED_CHANNELS:", REQUIRED_CHANNELS)
    BOT.run()
