import asyncio
import shutil
from pathlib import Path

PRESETS = {
    "480": {
        "height": 480,
        "crf": 28,
        "audio_bitrate": "96k",
    },
    "720": {
        "height": 720,
        "crf": 27,
        "audio_bitrate": "128k",
    },
    "1080": {
        "height": 1080,
        "crf": 27,
        "audio_bitrate": "128k",
    },
}


async def compress_video(
    input_file: str,
    output_file: str,
    quality: str
) -> None:

    if quality not in PRESETS:
        raise ValueError("Invalid quality")

    preset = PRESETS[quality]

    input_path = Path(input_file)
    output_path = Path(output_file)

    if not input_path.exists():
        raise FileNotFoundError(input_file)

    command = [
        "ffmpeg",
        "-y",

        "-i",
        str(input_path),

        "-vf",
        (
            f"scale="
            f"w='min(1280,iw)':"
            f"h='min({preset['height']},ih)':"
            f"force_original_aspect_ratio=decrease,"
            f"pad=ceil(iw/2)*2:ceil(ih/2)*2"
        ),

        "-c:v",
        "libx264",

        "-preset",
        "medium",

        "-crf",
        str(preset["crf"]),

        "-c:a",
        "aac",

        "-b:a",
        preset["audio_bitrate"],

        "-movflags",
        "+faststart",

        str(output_path),
    ]

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error = stderr.decode(
            "utf-8",
            errors="replace"
        )

        raise RuntimeError(
            f"FFmpeg failed:\n{error[-4000:]}"
        )

    # اگر فایل فشرده‌شده بزرگ‌تر از فایل اصلی شد،
    # فایل اصلی را جایگزین خروجی می‌کنیم.
    if output_path.exists():

        original_size = input_path.stat().st_size
        compressed_size = output_path.stat().st_size

        if compressed_size >= original_size:

            output_path.unlink()

            shutil.copy2(
                input_path,
                output_path
            )
