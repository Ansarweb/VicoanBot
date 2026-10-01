import os
import re
import shutil
import tempfile
import asyncio
import json
import traceback
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

MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB

LOCAL_API = "http://127.0.0.1:8081/bot"
LOCAL_FILE_API = "http://127.0.0.1:8081/file/bot"


INSTAGRAM_REGEX = re.compile(
    r"https?://(?:www\.)?instagram\.com/"
    r"(?:reel|reels|p|tv)/[^\s]+",
    re.IGNORECASE,
)


def format_size(size_bytes):
    if size_bytes is None:
        return "نامشخص"

    size = float(size_bytes)

    if size < 1024:
        return f"{size:.0f} B"

    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"

    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"

    return f"{size / (1024 * 1024 * 1024):.2f} GB"


def reduction_percent(original_size, final_size):
    if not original_size or original_size <= 0:
        return 0

    return max(
        0,
        round((1 - (final_size / original_size)) * 100)
    )


def prepare_caption(caption):
    if not caption:
        return None

    caption = str(caption).strip()

    if not caption:
        return None

    if len(caption) <= 1024:
        return caption

    return caption[:1000].rstrip() + "\n\n…"


async def send_video(
    message,
    video_path,
    caption=None,
    original_size=None,
):
    final_size = os.path.getsize(video_path)

    reduction = reduction_percent(
        original_size,
        final_size
    )

    info_lines = []

    if original_size:
        info_lines.append(
            f"حجم اولیه: {format_size(original_size)}"
        )

    info_lines.append(
        f"حجم نهایی: {format_size(final_size)}"
    )

    if original_size:
        info_lines.append(
            f"کاهش حجم: {reduction}%"
        )

    info_text = "\n".join(info_lines)

    if caption:
        combined_caption = (
            caption
            + "\n\n"
            + info_text
        )
    else:
        combined_caption = info_text

    combined_caption = prepare_caption(
        combined_caption
    )

    with open(video_path, "rb") as video_file:
        await message.reply_video(
            video=video_file,
            caption=combined_caption,
            supports_streaming=True,
        )


async def run_compression(
    input_path,
    output_path,
):
    try:
        result = await compress_video(
            input_path,
            output_path,
            "480",
        )

        if not os.path.exists(output_path):
            raise RuntimeError(
                "compress_video اجرا شد اما فایل خروجی ساخته نشد.\n\n"
                "نتیجه تابع:\n"
                + str(result)
            )

        return True, None

    except Exception as e:
        error_text = (
            "نوع خطا: "
            + type(e).__name__
            + "\n\n"
            + "پیام خطا:\n"
            + str(e)
        )

        print(
            "========== COMPRESSION ERROR =========="
        )
        print(error_text)

        traceback.print_exc()

        print(
            "======================================="
        )

        return False, error_text


async def process_telegram_video(
    message,
    file_id,
    file_name="video.mp4",
    caption=None,
):
    temp_dir = tempfile.mkdtemp(
        prefix="vicoan_"
    )

    try:
        input_path = os.path.join(
            temp_dir,
            file_name
        )

        output_path = os.path.join(
            temp_dir,
            "compressed_480p.mp4"
        )

        status_message = await message.reply_text(
            "⏳ در حال دانلود و فشرده‌سازی ویدیو...\n"
            "کیفیت خروجی: 480p"
        )

        telegram_file = await message.get_bot().get_file(
            file_id
        )

        await telegram_file.download_to_drive(
            input_path
        )

        original_size = os.path.getsize(
            input_path
        )

        if original_size > MAX_FILE_SIZE:
            await status_message.edit_text(
                "❌ حجم فایل بیشتر از 2 گیگابایت است."
            )
            return

        success, error_text = await run_compression(
            input_path,
            output_path
        )

        if not success:
            await status_message.edit_text(
                "❌ خطای واقعی فشرده‌سازی:\n\n"
                + error_text
            )
            return

        await status_message.edit_text(
            "📤 فشرده‌سازی انجام شد.\n"
            "در حال ارسال ویدیوی 480p..."
        )

        await send_video(
            message=message,
            video_path=output_path,
            caption=caption,
            original_size=original_size,
        )

        await status_message.delete()

    except Exception as e:
        error_text = (
            "نوع خطا: "
            + type(e).__name__
            + "\n\n"
            + "پیام:\n"
            + str(e)
        )

        print(
            "Telegram processing error:"
        )

        traceback.print_exc()

        try:
            await message.reply_text(
                "❌ خطای پردازش:\n\n"
                + error_text
            )
        except Exception:
            pass

    finally:
        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )


async def handle_video(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    message = update.effective_message

    if not message or not message.video:
        return

    video = message.video

    if (
        video.file_size
        and video.file_size > MAX_FILE_SIZE
    ):
        await message.reply_text(
            "❌ حجم ویدیو بیشتر از 2 گیگابایت است."
        )
        return

    await process_telegram_video(
        message=message,
        file_id=video.file_id,
        file_name="telegram_video.mp4",
        caption=message.caption,
    )


async def handle_document(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    message = update.effective_message

    if not message or not message.document:
        return

    document = message.document

    mime_type = document.mime_type or ""

    if not mime_type.startswith("video/"):
        await message.reply_text(
            "❌ این فایل ویدیویی نیست."
        )
        return

    if (
        document.file_size
        and document.file_size > MAX_FILE_SIZE
    ):
        await message.reply_text(
            "❌ حجم فایل بیشتر از 2 گیگابایت است."
        )
        return

    file_name = (
        document.file_name
        or "telegram_video.mp4"
    )

    await process_telegram_video(
        message=message,
        file_id=document.file_id,
        file_name=file_name,
        caption=message.caption,
    )


async def download_instagram_video(
    url,
    output_dir,
):
    output_template = os.path.join(
        output_dir,
        "instagram_video.%(ext)s"
    )

    command = [
        "yt-dlp",
        "--no-playlist",
        "--format",
        "bestvideo+bestaudio/best",
        "--merge-output-format",
        "mp4",
        "--write-info-json",
        "--no-warnings",
        "--restrict-filenames",
        "--extractor-args",
        "instagram:skip_auth=False",
        "-o",
        output_template,
        url,
    ]

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_text = stderr.decode(
            "utf-8",
            errors="ignore"
        ).strip()

        raise RuntimeError(
            error_text
            or "دانلود اینستاگرام ناموفق بود."
        )

    video_files = []

    for path in Path(output_dir).glob(
        "instagram_video.*"
    ):
        if path.suffix.lower() not in (
            ".json",
            ".part",
            ".ytdl",
        ):
            video_files.append(path)

    if not video_files:
        raise RuntimeError(
            "فایل ویدیویی اینستاگرام پیدا نشد."
        )

    video_path = video_files[0]

    caption = None

    # پیدا کردن فایل اطلاعات اینستاگرام
    info_files = list(
        Path(output_dir).glob(
            "instagram_video*.info.json"
        )
    )

    if info_files:
        info_path = info_files[0]

        try:
            with open(
                info_path,
                "r",
                encoding="utf-8"
            ) as f:
                info = json.load(f)

            # تلاش برای پیدا کردن کپشن
            caption = (
                info.get("description")
                or info.get("caption")
                or info.get("title")
                or info.get("fulltitle")
                or None
            )

            if caption:
                print(
                    "========== INSTAGRAM CAPTION =========="
                )
                print(
                    str(caption)[:2000]
                )
                print(
                    "======================================="
                )
            else:
                print(
                    "Instagram caption was not found."
                )

        except Exception as e:
            print(
                "Instagram metadata error:",
                repr(e)
            )

    return str(video_path), caption


async def handle_instagram_link(
    message,
    url,
):
    temp_dir = tempfile.mkdtemp(
        prefix="vicoan_instagram_"
    )

    try:
        status_message = await message.reply_text(
            "📥 در حال دریافت ویدیوی اینستاگرام..."
        )

        video_path, instagram_caption = (
            await download_instagram_video(
                url,
                temp_dir
            )
        )

        original_size = os.path.getsize(
            video_path
        )

        if original_size > MAX_FILE_SIZE:
            await status_message.edit_text(
                "❌ حجم ویدیوی اینستاگرام بیشتر "
                "از 2 گیگابایت است."
            )
            return

        compressed_path = os.path.join(
            temp_dir,
            "instagram_480p.mp4"
        )

        await status_message.edit_text(
            "⚙️ در حال فشرده‌سازی...\n"
            "کیفیت خروجی: 480p"
        )

        success, error_text = await run_compression(
            video_path,
            compressed_path
        )

        if not success:
            await status_message.edit_text(
                "❌ خطای واقعی فشرده‌سازی:\n\n"
                + error_text
            )
            return

        await status_message.edit_text(
            "📤 آماده شد.\n"
            "در حال ارسال ویدیوی 480p..."
        )

        await send_video(
            message=message,
            video_path=compressed_path,
            caption=instagram_caption,
            original_size=original_size,
        )

        await status_message.delete()

    except Exception as e:
        error_text = (
            "نوع خطا: "
            + type(e).__name__
            + "\n\n"
            + "پیام:\n"
            + str(e)
        )

        print(
            "Instagram processing error:"
        )

        traceback.print_exc()

        try:
            await message.reply_text(
                "❌ خطای پردازش اینستاگرام:\n\n"
                + error_text
            )
        except Exception:
            pass

    finally:
        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )


async def handle_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    message = update.effective_message

    if not message or not message.text:
        return

    match = INSTAGRAM_REGEX.search(
        message.text
    )

    if not match:
        return

    url = match.group(0).rstrip(
        ".,!?)]}"
    )

    await handle_instagram_link(
        message,
        url
    )


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.effective_message.reply_text(
        "سلام 👋\n\n"
        "🎬 ویدیوی تلگرام را بفرستید؛ "
        "به‌صورت خودکار به 480p فشرده می‌شود.\n\n"
        "📸 لینک عمومی پست یا ریل اینستاگرام "
        "را هم بفرستید تا دانلود و به 480p تبدیل شود.\n\n"
        "📝 کپشن و توضیحات ویدیو نیز تا حد امکان "
        "همراه ویدیوی خروجی حفظ می‌شود.\n\n"
        "❌ نیازی به انتخاب کیفیت نیست."
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN پیدا نشد."
        )

    request = HTTPXRequest(
        connection_pool_size=20,
        connect_timeout=60,
        read_timeout=1800,
        write_timeout=1800,
        pool_timeout=60,
    )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(request)
        .base_url(LOCAL_API)
        .base_file_url(LOCAL_FILE_API)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text,
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
        "VicoanBot started."
    )

    application.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
