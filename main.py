import os
import play_scraper
from pyrogram import Client, filters
from pyrogram.types import *

# ==========================
#  YOUR BOT DETAILS ADDED
# ==========================

Bot = Client(
    "Play-Store-Bot",
    bot_token = os.environ["BOT_TOKEN"],   # Your bot token from BotFather
    api_id = int(os.environ["API_ID"]),    # Your Telegram API ID
    api_hash = os.environ["API_HASH"]      # Your Telegram API Hash
)

# ==========================
#   /start (Private Chat)
# ==========================

@Bot.on_message(filters.private & filters.all)
async def filter_all(bot, update):
    text = "Search play store apps using the buttons below.\n\nMade by @fe"   # <--- Your name added here

    reply_markup = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(text="Search here", switch_inline_query_current_chat="")],
            [InlineKeyboardButton(text="Search in another chat", switch_inline_query="")]
        ]
    )

    await update.reply_text(
        text=text,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
        quote=True
    )


# ==========================
#   Inline Query
# ==========================

@Bot.on_inline_query()
async def search(bot, update):
    results = play_scraper.search(update.query)
    answers = []

    for result in results:
        details = (
            "**Title:** `{}`\n"
            "**Description:** `{}`\n"
            "**App ID:** `{}`\n"
            "**Developer:** `{}`\n"
            "**Developer ID:** `{}`\n"
            "**Score:** `{}`\n"
            "**Price:** `{}`\n"
            "**Full Price:** `{}`\n"
            "**Free:** `{}`\n\n"
            "Made by @fe"   # <--- Your name added here
        ).format(
            result.get("title", "N/A"),
            result.get("description", "N/A"),
            result.get("app_id", "N/A"),
            result.get("developer", "N/A"),
            result.get("developer_id", "N/A"),
            result.get("score", "N/A"),
            result.get("price", "N/A"),
            result.get("full_price", "N/A"),
            result.get("free", "N/A")
        )

        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton(text="Play Store", url="https://play.google.com" + result["url"])]]
        )

        try:
            answers.append(
                InlineQueryResultArticle(
                    title=result["title"],
                    description=result.get("description", None),
                    thumb_url=result.get("icon", None),
                    input_message_content=InputTextMessageContent(
                        message_text=details,
                        disable_web_page_preview=True
                    ),
                    reply_markup=reply_markup
                )
            )
        except Exception as error:
            print(error)

    await update.answer(answers)

# ==========================
#   Run the Bot
# ==========================

Bot.run()
