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

    return match.group(0).rstrip(
        ".,!?;:)]}"
    )


# ============================================================
# /start
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

    input_file = work_dir / "input.mp4"
    output_file = work_dir / "vicoan_480p.mp4"

    status_message = None

    try:

        # ----------------------------------------------------
        # Download
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Compress
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Upload
        # ----------------------------------------------------

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
            error_text = repr(error)

        await message.reply_text(
            "❌ هنگام پردازش فایل خطایی رخ داد.\n\n"
            f"نوع خطا:\n"
            f"{type(error).__name__}\n\n"
            f"جزئیات:\n"
            f"{error_text[:3000]}"
        )

    finally:

        shutil.rmtree(
            work_dir,
            ignore_errors=True,
        )


# ============================================================
# Telegram normal video
# ============================================================

async def handle_video(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    message = update.message

    if not message or not message.video:
        return

    video = message.video

    if (
        video.file_size
        and video.file_size > MAX_FILE_SIZE
    ):

        await message.reply_text(
            "❌ حجم فایل بیشتر از ۲ گیگابایت است."
        )

        return

    await process_telegram_video(
        message=message,
        context=context,
        file_id=video.file_id,
    )


# ============================================================
# Telegram video sent as document
# ============================================================

async def handle_document(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    message = update.message

    if not message or not message.document:
        return

    document = message.document

    mime_type = document.mime_type or ""

    if not mime_type.startswith("video/"):

        await message.reply_text(
            "❌ این فایل ویدئویی نیست."
        )

        return

    if (
        document.file_size
        and document.file_size > MAX_FILE_SIZE
    ):

        await message.reply_text(
            "❌ حجم فایل بیشتر از ۲ گیگابایت است."
        )

        return

    await process_telegram_video(
        message=message,
        context=context,
        file_id=document.file_id,
    )


# ============================================================
# Instagram downloader
# ============================================================

async def download_instagram_video(
    url: str,
    output_dir: Path,
) -> Path:

    output_template = (
        output_dir
        / "instagram_video.%(ext)s"
    )

    command = [
        "yt-dlp",

        "--no-playlist",

        "--format",
        "bestvideo+bestaudio/best",

        "--merge-output-format",
        "mp4",

        "--no-warnings",

        "--restrict-filenames",

        "-o",
        str(output_template),

        url,
    ]

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    stdout_text = stdout.decode(
        "utf-8",
        errors="replace",
    )

    stderr_text = stderr.decode(
        "utf-8",
        errors="replace",
    )

    if process.returncode != 0:

        error_text = stderr_text[-5000:]

        if not error_text:
            error_text = stdout_text[-5000:]

        raise RuntimeError(
            "Instagram download failed:\n"
            + error_text
        )

    video_files = []

    for file in output_dir.iterdir():

        if (
            file.is_file()
            and file.suffix.lower()
            in (
                ".mp4",
                ".mkv",
                ".webm",
                ".mov",
                ".avi",
            )
        ):

            video_files.append(file)

    if not video_files:

        raise RuntimeError(
            "Instagram video was downloaded, "
            "but the video file could not be found."
        )

    return max(
        video_files,
        key=lambda item: item.stat().st_mtime,
    )


# ============================================================
# Instagram link handler
# ============================================================

async def handle_instagram_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    message = update.message

    if not message or not message.text:
        return

    url = extract_instagram_url(
        message.text
    )

    if not url:
        return

    work_dir = Path(
        tempfile.mkdtemp(
            prefix="vicoan_instagram_"
        )
    )

    output_file = (
        work_dir
        / "instagram_480p.mp4"
    )

    status_message = None

    try:

        # ----------------------------------------------------
        # Download Instagram
        # ----------------------------------------------------

        status_message = await message.reply_text(
            "📥 لینک Instagram دریافت شد.\n\n"
            "در حال دانلود ویدئو..."
        )

        downloaded_file = (
            await download_instagram_video(
                url=url,
                output_dir=work_dir,
            )
        )

        if not downloaded_file.exists():

            raise RuntimeError(
                "فایل Instagram دریافت نشد."
            )

        downloaded_size = (
            downloaded_file.stat().st_size
        )

        if downloaded_size > MAX_FILE_SIZE:

            raise RuntimeError(
                "حجم ویدئوی دانلودشده بیشتر از "
                "۲ گیگابایت است."
            )

        # ----------------------------------------------------
        # Compress Instagram video
        # ----------------------------------------------------

        await status_message.edit_text(
            "⚙️ ویدئو دانلود شد.\n\n"
            "در حال تبدیل به 480p و "
            "کاهش حجم..."
        )

        await compress_video(
            input_file=str(downloaded_file),
            output_file=str(output_file),
            quality="480",
        )

        if not output_file.exists():

            raise RuntimeError(
                "فایل 480p ساخته نشد."
            )

        if output_file.stat().st_size == 0:

            raise RuntimeError(
                "فایل خروجی خالی است."
            )

        # ----------------------------------------------------
        # Send Instagram video
        # ----------------------------------------------------

        await status_message.edit_text(
            "⬆️ فشرده‌سازی تمام شد.\n\n"
            "در حال ارسال نسخه کم‌حجم..."
        )

        compressed_size = (
            output_file.stat().st_size
        )

        original_mb = (
            downloaded_size
            / 1024
            / 1024
        )

        compressed_mb = (
            compressed_size
            / 1024
            / 1024
        )

        reduction = 0

        if downloaded_size > 0:

            reduction = (
                1
                - (
                    compressed_size
                    / downloaded_size
                )
            ) * 100

        caption = (
            "✅ ویدئوی Instagram آماده شد.\n\n"
            "🎬 کیفیت: 480p\n"
            f"📦 حجم اولیه: {original_mb:.1f} MB\n"
            f"📦 حجم نهایی: {compressed_mb:.1f} MB\n"
            f"📉 کاهش حجم: {reduction:.0f}%"
        )

        with output_file.open("rb") as video_file:

            await message.reply_video(
                video=video_file,
                caption=caption,
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
            error_text = repr(error)

        await message.reply_text(
            "❌ پردازش لینک Instagram انجام نشد.\n\n"
            f"نوع خطا:\n"
            f"{type(error).__name__}\n\n"
            f"جزئیات:\n"
            f"{error_text[:3000]}"
        )

    finally:

        shutil.rmtree(
            work_dir,
            ignore_errors=True,
        )


# ============================================================
# Main
# ============================================================

def main():

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .base_url(LOCAL_API)
        .base_file_url(LOCAL_FILE_API)
        .request(TELEGRAM_REQUEST)
        .build()
    )

    # --------------------------------------------------------
    # /start
    # --------------------------------------------------------

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    # --------------------------------------------------------
    # Instagram links
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_instagram_link,
        )
    )

    # --------------------------------------------------------
    # Normal Telegram videos
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.VIDEO,
            handle_video,
        )
    )

    # --------------------------------------------------------
    # Telegram videos sent as documents
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.Document.VIDEO,
            handle_document,
        )
    )

    print(
        "VicoanBot is running on Local Bot API...",
        flush=True,
    )

    application.run_polling()


if __name__ == "__main__":
    main()
