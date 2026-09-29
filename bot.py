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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام 👋\n\n"
        "من ربات فشرده‌سازی ویدئو هستم.\n"
        "یک ویدئو برای من بفرست یا Forward کن.\n\n"
        "بعد از دریافت ویدئو، کیفیت موردنظر را انتخاب کن."
    )


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    if not message:
        return

    video = message.video

    if not video:
        await message.reply_text("لطفاً یک فایل ویدئویی ارسال کن.")
        return

    if video.file_size and video.file_size > MAX_FILE_SIZE:
        await message.reply_text(
            "حجم این فایل بیشتر از ۲ گیگابایت است."
        )
        return

    context.user_data["video_file_id"] = video.file_id

    keyboard = [
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

    await message.reply_text(
        "کیفیت خروجی را انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    await query.answer()

    file_id = context.user_data.get("video_file_id")

    if not file_id:
        await query.message.reply_text(
            "فایل ویدئویی پیدا نشد. دوباره ویدئو را ارسال کن."
        )
        return

    quality = query.data.replace("quality_", "")

    await query.edit_message_text(
        f"⏳ در حال آماده‌سازی نسخه {quality}p...\n"
        "ممکن است برای فایل‌های بزرگ مدتی طول بکشد."
    )

    work_dir = Path(tempfile.mkdtemp(prefix="vicoan_"))

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
            raise RuntimeError("Output file was not created")

        await query.message.reply_video(
            video=output_file.open("rb"),
            caption=f"✅ نسخه {quality}p آماده شد.",
            supports_streaming=True,
        )

    except Exception as error:
        await query.message.reply_text(
            "❌ هنگام فشرده‌سازی خطایی رخ داد.\n\n"
            f"{str(error)[:1500]}"
        )

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "این فایل به‌صورت Document ارسال شده است.\n"
        "فعلاً لطفاً ویدئو را با گزینه Video ارسال کن."
    )


def main():
    application = Application.builder().token(BOT_TOKEN).build()

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

    print("VicoanBot is running...")

    application.run_polling()


if __name__ == "__main__":
    main()
