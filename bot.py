import os
import re
import shutil
import tempfile
import asyncio
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from compressor import compress_video


BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not configured")


MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024

LOCAL_API = "http://127.0.0.1:8081/bot"
LOCAL_FILE_API = "http://127.0.0.1:8081/file/bot"


# ============================================================
# Telegram connection settings
# مناسب برای فایل‌های حجیم
# ============================================================

TELEGRAM_REQUEST = HTTPXRequest(
    connection_pool_size=20,
    connect_timeout=60.0,
    read_timeout=1800.0,
    write_timeout=1800.0,
    pool_timeout=60.0,
)


# ============================================================
# Instagram URL detection
# ============================================================

INSTAGRAM_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?instagram\.com/"
    r"(?:reel|reels|p|tv)/[^\s]+",
    re.IGNORECASE,
)


def extract_instagram_url(text: str):
    if not text:
        return None

    match = INSTAGRAM_URL_PATTERN.search(text)

    if not match:
        return None

    url = match.group(0)

    # حذف علائم احتمالی انتهای لینک
    url = url.rstrip(".,!?;:)]}")

    return url


# ============================================================
# Start
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "سلام 👋\n\n"
        "من ربات فشرده‌سازی ویدئو هستم.\n\n"
        "🎬 ویدئوی تلگرامی بفرست:\n"
        "ربات مستقیم آن را به 480p تبدیل و کم‌حجم می‌کند.\n\n"
        "📥 یا لینک Instagram بفرست:\n"
        "ربات خودش ویدئو را دانلود می‌کند، "
        "به 480p تبدیل می‌کند و نسخه کم‌حجم را تحویل می‌دهد."
    )


# ============================================================
# Telegram video processor
# ============================================================

async def process_telegram_video(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    file_id: str,
):

    work_dir = Path(
        tempfile.mkdtemp(
            prefix="vicoan_"
        )
    )

    input_file = (
        work_dir
        / "input.mp4"
    )

    output_file = (
        work_dir
        / "vicoan_480p.mp4"
    )

    status_message = None

    try:

        # ====================================================
        # Download Telegram video
        # ====================================================

        status_message = await message.reply_text(
            "⬇️ ویدئو دریافت شد.\n\n"
            "در حال دریافت فایل..."
        )

        telegram_file = await context.bot.get_file(
            file_id
        )

        await telegram_file.download_to_drive(
            custom_path=str(input_file)
        )

        if not input_file.exists():

            raise RuntimeError(
                "فایل ورودی دانلود نشد."
            )

        # ====================================================
        # Compression
        # ====================================================

        await status_message.edit_text(
            "⚙️ فایل دریافت شد.\n\n"
            "در حال فشرده‌سازی به 480p..."
        )

        await compress_video(
            input_file=str(input_file),
            output_file=str(output_file),
            quality="480",
        )

        if not output_file.exists():

            raise RuntimeError(
                "فایل خروجی ساخته نشد."
            )

        if output_file.stat().st_size == 0:

            raise RuntimeError(
                "فایل خروجی خالی است."
            )

        # ====================================================
        # Upload
        # ====================================================

        await status_message.edit_text(
            "⬆️ فشرده‌سازی تمام شد.\n\n"
            "در حال ارسال نسخه کم‌حجم..."
        )

        with output_file.open("rb") as video_file:

            await message.reply_video(
                video=video_file,
                caption="✅ نسخه 480p آماده شد.",
                supports_streaming=True,
                read_timeout=1800,
                write_timeout=1800,
                connect_timeout=60,
                pool_timeout=60,
            )

        await status_message.delete()

    except Exception as error:

        error_text = str(error)

        if not error_text:
            error_text =
