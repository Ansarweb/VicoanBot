import asyncio
import shutil
from pathlib import Path


PRESETS = {
    "480": {
        "height": 480,
        "crf": 32,
        "audio_bitrate": "64k",
    },
    "720": {
        "height": 720,
        "crf": 31,
        "audio_bitrate": "64k",
    },
    "1080": {
        "height": 1080,
        "crf": 30,
        "audio_bitrate": "64k",
    },
}


async def compress_video(
    input_file: str,
    output_file: str,
    quality: str
) -> None:

    if quality not in PRESETS:
        raise ValueError(
            f"Invalid quality: {quality}"
        )

    preset = PRESETS[quality]

    input_path = Path(input_file)
    output_path = Path(output_file)

    if not input_path.exists():
        raise FileNotFoundError(
            f"Input file not found: {input_file}"
        )

    # --------------------------------------------------------
    # FFmpeg
    # --------------------------------------------------------

    command = [
        "ffmpeg",
        "-y",

        "-i",
        str(input_path),

        # کاهش رزولوشن در صورت نیاز
        "-vf",
        (
            f"scale="
            f"w='min(1280,iw)':"
            f"h='min({preset['height']},ih)':"
            f"force_original_aspect_ratio=decrease,"
            f"pad=ceil(iw/2)*2:ceil(ih/2)*2"
        ),

        # H.264
        "-c:v",
        "libx264",

        # فشرده‌سازی شدید
        "-preset",
        "slow",

        "-crf",
        str(preset["crf"]),

        # صدای کم‌حجم
        "-c:a",
        "aac",

        "-b:a",
        preset["audio_bitrate"],

        "-ac",
        "2",

        # سازگاری بهتر با Telegram
        "-pix_fmt",
        "yuv420p",

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
            "FFmpeg compression failed:\n"
            + error[-5000:]
        )

    if not output_path.exists():

        raise RuntimeError(
            "FFmpeg did not create output file."
        )

    if output_path.stat().st_size == 0:

        raise RuntimeError(
            "FFmpeg created an empty output file."
        )

    # --------------------------------------------------------
    # جلوگیری از بزرگ‌تر شدن فایل
    # --------------------------------------------------------

    original_size = input_path.stat().st_size
    compressed_size = output_path.stat().st_size

    if compressed_size >= original_size:

        output_path.unlink()

        shutil.copy2(
            input_path,
            output_path
        )
