import os
import re
import time
import sqlite3
import asyncio
import logging
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from telegram import Bot
from telegram.error import TelegramError, RetryAfter


# =========================================================
# CONFIG
# =========================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@ByteTunnelnews")
SITE_URL = "https://www.shahrekhabar.com/"

CHECK_INTERVAL = int(
    os.getenv("CHECK_INTERVAL", "120")
)

DB_FILE = "news.db"

SIGNATURE = "📢 @ByteTunnelnews"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 15) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/139.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

log = logging.getLogger("ShahrekhabarBot")


# =========================================================
# TOKEN CHECK
# =========================================================

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN در فایل .env پیدا نشد."
    )


# =========================================================
# DATABASE
# =========================================================

def init_db():

    conn = sqlite3.connect(DB_FILE)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sent_news (
            news_id TEXT PRIMARY KEY,
            title TEXT,
            url TEXT,
            sent_at INTEGER
        )
    """)

    conn.commit()
    conn.close()


def is_sent(news_id):

    conn = sqlite3.connect(DB_FILE)

    row = conn.execute(
        """
        SELECT news_id
        FROM sent_news
        WHERE news_id = ?
        LIMIT 1
        """,
        (news_id,)
    ).fetchone()

    conn.close()

    return row is not None


def mark_sent(news_id, title, url):

    conn = sqlite3.connect(DB_FILE)

    conn.execute(
        """
        INSERT OR IGNORE INTO sent_news
        (news_id, title, url, sent_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            news_id,
            title,
            url,
            int(time.time())
        )
    )

    conn.commit()
    conn.close()


def mark_many_as_seen(news):

    if not news:
        return

    conn = sqlite3.connect(DB_FILE)

    for item in news:

        conn.execute(
            """
            INSERT OR IGNORE INTO sent_news
            (news_id, title, url, sent_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                item["id"],
                item["title"],
                item["url"],
                int(time.time())
            )
        )

    conn.commit()
    conn.close()


def database_is_empty():

    conn = sqlite3.connect(DB_FILE)

    row = conn.execute(
        "SELECT COUNT(*) FROM sent_news"
    ).fetchone()

    conn.close()

    return row[0] == 0


# =========================================================
# HTTP
# =========================================================

session = requests.Session()

session.headers.update(
    HEADERS
)


# =========================================================
# HELPERS
# =========================================================

def clean_text(text):

    if not text:
        return ""

    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


def get_news_id(url):

    match = re.search(
        r"/news/([^/?#]+)",
        url
    )

    if match:
        return match.group(1)

    return url


# =========================================================
# DOWNLOAD HOMEPAGE
# =========================================================

def fetch_homepage():

    for attempt in range(1, 6):

        try:

            log.info(
                "Downloading homepage - attempt %d/3",
                attempt
            )

            response = session.get(
                SITE_URL,
                timeout=(10, 25)
            )

            response.raise_for_status()

            response.encoding = (
                response.apparent_encoding
                or "utf-8"
            )

            log.info(
                "Homepage downloaded: %d bytes",
                len(response.content)
            )

            return response.text

        except requests.RequestException as e:

            log.warning(
                "Homepage connection error: %s",
                e
            )

            if attempt < 5:
                time.sleep(5)

    return None


# =========================================================
# EXTRACT NEWS
# =========================================================

def extract_news(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    results = []
    seen = set()

    for a in soup.find_all(
        "a",
        href=True
    ):

        href = a.get(
            "href",
            ""
        ).strip()

        if "/news/" not in href:
            continue

        url = urljoin(
            SITE_URL,
            href
        )

        news_id = get_news_id(
            url
        )

        if news_id in seen:
            continue

        title = clean_text(
            a.get_text(
                " ",
                strip=True
            )
        )

        if len(title) < 8:
            continue

        seen.add(news_id)

        results.append({
            "id": news_id,
            "title": title,
            "url": url
        })

    return results


# =========================================================
# ARTICLE
# =========================================================

def fetch_article(url):

    try:

        response = session.get(
            url,
            timeout=(20, 60)
        )

        response.raise_for_status()

        response.encoding = (
            response.apparent_encoding
            or "utf-8"
        )

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        # -------------------------------------------------
        # TITLE
        # -------------------------------------------------

        title = ""

        og_title = soup.find(
            "meta",
            attrs={
                "property": "og:title"
            }
        )

        if og_title:

            title = clean_text(
                og_title.get(
                    "content",
                    ""
                )
            )

        if not title:

            h1 = soup.find("h1")

            if h1:

                title = clean_text(
                    h1.get_text(
                        " ",
                        strip=True
                    )
                )

        if not title and soup.title:

            title = clean_text(
                soup.title.get_text(
                    " ",
                    strip=True
                )
            )

        # -------------------------------------------------
        # DESCRIPTION
        # -------------------------------------------------

        description = ""

        meta_desc = soup.find(
            "meta",
            attrs={
                "name": "description"
            }
        )

        if meta_desc:

            description = clean_text(
                meta_desc.get(
                    "content",
                    ""
                )
            )

        if not description:

            og_desc = soup.find(
                "meta",
                attrs={
                    "property": "og:description"
                }
            )

            if og_desc:

                description = clean_text(
                    og_desc.get(
                        "content",
                        ""
                    )
                )

        # -------------------------------------------------
        # ARTICLE TEXT
        # -------------------------------------------------

        article_text = ""

        article = (
            soup.find("article")
            or soup.find(
                class_=re.compile(
                    "article",
                    re.I
                )
            )
            or soup.find(
                class_=re.compile(
                    "news-content",
                    re.I
                )
            )
            or soup.find(
                class_=re.compile(
                    "content",
                    re.I
                )
            )
        )

        if article:

            paragraphs = []

            for p in article.find_all("p"):

                text = clean_text(
                    p.get_text(
                        " ",
                        strip=True
                    )
                )

                if len(text) >= 30:
                    paragraphs.append(
                        text
                    )

            article_text = " ".join(
                paragraphs[:8]
            )

        if not description:
            description = article_text

        return {
            "title": title,
            "description": description,
            "url": url
        }

    except Exception as e:

        log.warning(
            "Article fetch error: %s",
            e
        )

        return None


# =========================================================
# MESSAGE
# =========================================================

def build_message(article):

    description = clean_text(
        article.get(
            "description",
            ""
        )
    )

    description = re.sub(
        r"<[^>]+>",
        "",
        description
    )

    description = re.sub(
        r"\s+",
        " ",
        description
    ).strip()

    if len(description) > 500:
        description = (
            description[:500]
            .rsplit(" ", 1)[0]
            + "..."
        )

    if not description:
        description = "خبر جدید منتشر شد."

    message = (
        description
        + "\\n\\n"
        + "📢 @ByteTunnelnews"
    )

    return message


# =========================================================
# SEND
# =========================================================

async def send_news(
    bot,
    article
):

    message = build_message(
        article
    )

    try:

        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=message,
            parse_mode="HTML",
            disable_web_page_preview=False
        )

        log.info(
            "Sent: %s",
            article.get(
                "title",
                "Unknown"
            )
        )

        return True

    except RetryAfter as e:

        wait_time = (
            int(e.retry_after)
            + 2
        )

        log.warning(
            "Flood control: waiting %d seconds",
            wait_time
        )

        await asyncio.sleep(
            wait_time
        )

        return await send_news(
            bot,
            article
        )

    except TelegramError as e:

        log.error(
            "Telegram send error: %s",
            e
        )

        return False


# =========================================================
# CHECK NEWS
# =========================================================

async def check_news(bot):

    log.info(
        "Checking Shahrekhabar..."
    )

    html = fetch_homepage()

    if not html:

        log.warning(
            "Could not download Shahrekhabar"
        )

        return

    news = extract_news(
        html
    )

    log.info(
        "Found %d news links",
        len(news)
    )

    if not news:
        return

    # =====================================================
    # FIRST RUN
    # =====================================================

    if database_is_empty():

        log.info(
            "First run detected."
        )

        log.info(
            "Marking current news as already seen."
        )

        mark_many_as_seen(
            news
        )

        log.info(
            "Initial news saved: %d",
            len(news)
        )

        log.info(
            "No old news will be sent."
        )

        return

    # =====================================================
    # NEW NEWS
    # =====================================================

    new_news = []

    for item in news:

        if not is_sent(
            item["id"]
        ):

            new_news.append(
                item
            )

    log.info(
        "New news: %d",
        len(new_news)
    )

    if not new_news:
        return

    # Oldest -> newest
    new_news.reverse()

    for item in new_news:

        article = fetch_article(
            item["url"]
        )

        if not article:

            article = {
                "title": item["title"],
                "description": "",
                "url": item["url"]
            }

        article["url"] = item["url"]

        success = await send_news(
            bot,
            article
        )

        if success:

            mark_sent(
                item["id"],
                item["title"],
                item["url"]
            )

            await asyncio.sleep(3)


# =========================================================
# MAIN
# =========================================================

async def main():

    init_db()

    bot = Bot(
        token=BOT_TOKEN
    )

    log.info("=" * 45)

    log.info(
        "Shahrekhabar News Bot"
    )

    log.info(
        "Channel: %s",
        CHANNEL_ID
    )

    log.info(
        "Interval: %s seconds",
        CHECK_INTERVAL
    )

    log.info("=" * 45)

    try:

        me = await bot.get_me()

        log.info(
            "Bot: @%s",
            me.username
        )

        # -------------------------------------------------
        # CHANNEL CHECK
        # -------------------------------------------------

        try:

            chat = await bot.get_chat(
                CHANNEL_ID
            )

            log.info(
                "Channel connected: %s",
                getattr(
                    chat,
                    "title",
                    CHANNEL_ID
                )
            )

        except TelegramError as e:

            log.error(
                "Channel access error: %s",
                e
            )

            return

        # -------------------------------------------------
        # LOOP
        # -------------------------------------------------

        while True:

            try:

                await check_news(
                    bot
                )

            except Exception as e:

                log.exception(
                    "Unexpected error: %s",
                    e
                )

            log.info(
                "Next check in %d seconds...",
                CHECK_INTERVAL
            )

            await asyncio.sleep(
                CHECK_INTERVAL
            )

    finally:

        await bot.shutdown()


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )
