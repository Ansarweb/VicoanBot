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
            f"{
