import os
import shutil
import tempfile
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
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
# مناسب برای فایل‌های حجیم و اینترنت کند
# ============================================================

TELEGRAM_REQUEST = HTTPXRequest(
    connection_pool_size=20,
    connect_timeout=60.0,
    read_timeout=1800.0,
    write_timeout=1800.0,
    pool_timeout=60.0,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "سلام 👋\n\n"
        "من ربات فشرده‌سازی ویدئو هستم.\n\n"
        "یک ویدئو برای من بفرست یا Forward کن.\n"
        "بعد کیفیت خروجی را انتخاب کن."
    )


def quality_keyboard():

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔹 کم‌حجم — 480p",
                    callback_data="quality_480",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔹 متعادل — 720p",
                    callback_data="quality_720",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔹 کیفیت بالا — 1080p",
                    callback_data="quality_1080",
                )
            ],
        ]
    )


async def handle_video(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    message = update.message

    if not message or not message.video:
        return

    video = message.video

    if video.file_size and video.file_size > MAX_FILE_SIZE:

        await message.reply_text(
            "❌ حجم فایل بیشتر از ۲ گیگابایت است."
        )

        return

    context.user_data["video_file_id"] = video.file_id

    await message.reply_text(
        "ویدئو دریافت شد.\n\n"
        "کیفیت خروجی را انتخاب کن:",
        reply_markup=quality_keyboard(),
    )


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

    if document.file_size and document.file_size > MAX_FILE_SIZE:

        await message.reply_text(
            "❌ حجم فایل بیشتر از ۲ گیگابایت است."
        )

        return

    context.user_data["video_file_id"] = document.file_id

    await message.reply_text(
        "ویدئو دریافت شد.\n\n"
        "کیفیت خروجی را انتخاب کن:",
        reply_markup=quality_keyboard(),
    )


async def handle_quality(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    file_id = context.user_data.get("video_file_id")

    if not file_id:

        await query.message.reply_text(
            "❌ فایل ویدئویی پیدا نشد.\n"
            "لطفاً دوباره ویدئو را ارسال کن."
        )

        return

    quality = query.data.replace(
        "quality_",
        "",
    )

    await query.edit_message_text(
        f"⏳ در حال فشرده‌سازی نسخه {quality}p...\n\n"
        "برای فایل‌های بزرگ ممکن است مدتی طول بکشد."
    )

    work_dir = Path(
        tempfile.mkdtemp(
            prefix="vicoan_"
        )
    )

    input_file = work_dir / "input.mp4"

    output_file = (
        work_dir
        / f"vicoan_{quality}p.mp4"
    )

    try:

        # ====================================================
        # Download
        # ====================================================

        await query.message.reply_text(
            "⬇️ در حال دریافت فایل..."
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

        await query.message.reply_text(
            "⚙️ فایل دریافت شد.\n"
            "در حال فشرده‌سازی..."
        )

        await compress_video(
            input_file=str(input_file),
            output_file=str(output_file),
            quality=quality,
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

        await query.message.reply_text(
            "⬆️ فشرده‌سازی تمام شد.\n"
            "در حال ارسال فایل..."
        )

        with output_file.open("rb") as video_file:

            await query.message.reply_video(
                video=video_file,
                caption=(
                    f"✅ نسخه {quality}p آماده شد."
                ),
                supports_streaming=True,
                read_timeout=1800,
                write_timeout=1800,
                connect_timeout=60,
                pool_timeout=60,
            )

    except Exception as error:

        error_text = str(error)

        if not error_text:
            error_text = repr(error)

        await query.message.reply_text(
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


def main():

    application = (
        Application.builder()
        .token(BOT_TOKEN)

        # Local Telegram Bot API
        .base_url(LOCAL_API)
        .base_file_url(LOCAL_FILE_API)

        # Timeoutهای طولانی برای فایل‌های حجیم
        .request(TELEGRAM_REQUEST)

        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            handle_quality,
            pattern=r"^quality_(480|720|1080)$",
        )
    )

    application.add_handler(
        MessageHandler(
            filters.VIDEO,
            handle_video,
        )
    )

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
