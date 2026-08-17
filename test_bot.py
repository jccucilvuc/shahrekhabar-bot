import os
import asyncio
from dotenv import load_dotenv
from telegram import Bot

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

async def main():
    if not TOKEN:
        print("❌ BOT_TOKEN پیدا نشد")
        return

    if not CHANNEL_ID:
        print("❌ CHANNEL_ID پیدا نشد")
        return

    bot = Bot(TOKEN)

    try:
        me = await bot.get_me()
        print(f"✅ بات شناسایی شد: @{me.username}")

        message = await bot.send_message(
            chat_id=CHANNEL_ID,
            text="✅ تست اتصال موفق بود!\n\n🤖 بات آماده دریافت اخبار است."
        )

        print("✅ پیام با موفقیت در کانال ارسال شد.")
        print(f"Message ID: {message.message_id}")

    except Exception as e:
        print("❌ خطا:")
        print(e)

    finally:
        await bot.shutdown()

asyncio.run(main())
