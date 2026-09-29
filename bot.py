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

from compressor import compress_video


BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not configured")


MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024

LOCAL_API = "http://127.0.0.1:8081/bot"
LOCAL_FILE_API = "http://127.0.0.1:8081/file/bot"


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


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


async def handle_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    await query.answer()

    file_id = context.user_data.get("video_file_id")

    if not file_id:
        await query.message.reply_text(
            "❌ فایل ویدئویی پیدا نشد.\n"
            "لطفاً دوباره ویدئو را ارسال کن."
        )
        return

    quality = query.data.replace("quality_", "")

    await query.edit_message_text(
        f"⏳ در حال فشرده‌سازی نسخه {quality}p...\n\n"
        "برای فایل‌های بزرگ ممکن است مدتی طول بکشد."
    )

    work_dir = Path(
        tempfile.mkdtemp(prefix="vicoan_")
    )

    input_file = work_dir / "input.mp4"
    output_file = work_dir / f"vicoan_{quality}p.mp4"

    try:
        telegram_file = await context.bot.get_file(file_id)

        await telegram_file.download_to_drive(
            custom_path=str(input_file)
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

        with output_file.open("rb") as video_file:
            await query.message.reply_video(
                video=video_file,
                caption=f"✅ نسخه {quality}p آماده شد.",
                supports_streaming=True,
            )

    except Exception as error:
        await query.message.reply_text(
            "❌ هنگام فشرده‌سازی خطایی رخ داد.\n\n"
            f"{str(error)[:1500]}"
        )

    finally:
        shutil.rmtree(
            work_dir,
            ignore_errors=True
        )


def main():

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .base_url(LOCAL_API)
        .base_file_url(LOCAL_FILE_API)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
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

    print("VicoanBot is running on Local Bot API...")

    application.run_polling()


if __name__ == "__main__":
    main()
