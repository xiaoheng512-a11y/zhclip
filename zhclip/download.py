"""
zhclip.download - 视频下载模块
封装 yt-dlp 用于下载各种平台的视频/音频
"""

import os
import sys
import subprocess
import logging
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger("zhclip.download")


def _find_ytdlp() -> str:
    """查找 yt-dlp 可执行文件（兼容 Windows venv）"""
    candidates = [
        "yt-dlp",
        "yt-dlp.exe",
        str(Path(sys.prefix) / "Scripts" / "yt-dlp.exe"),
        str(Path(sys.prefix) / "bin" / "yt-dlp"),
    ]
    for c in candidates:
        try:
            subprocess.run([c, "--version"], capture_output=True, timeout=5)
            return c
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    raise RuntimeError("找不到 yt-dlp。请执行: pip install yt-dlp")


YTDLP = _find_ytdlp()


def download_audio(
    url: str,
    output_dir: Optional[str] = None,
    format: str = "wav",
    quality: str = "0",
) -> str:
    """
    下载在线视频/音频并转为指定格式。

    支持: YouTube, Bilibili, TikTok, X/Twitter, Instagram, 抖音, 快手等

    参数:
        url: 视频 URL
        output_dir: 输出目录（默认临时目录）
        format: 输出格式 (wav/mp3/m4a)
        quality: 音频质量 (0=最好, 10=最差)

    返回:
        下载文件路径
    """
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        tmp_dir = None
    else:
        tmp_dir = tempfile.mkdtemp()
        output_dir = tmp_dir

    output_template = os.path.join(output_dir, "%(title)s.%(ext)s")

    try:
        cmd = [
            YTDLP,
            "-x",
            "--audio-format", format,
            "--audio-quality", quality,
            "-o", output_template,
            "--no-playlist",
            "--print", "filename",
            "--no-warnings",
            url,
        ]

        logger.info(f"下载: {url}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            error_msg = result.stderr[:500] if result.stderr else "未知错误"
            raise RuntimeError(f"下载失败: {error_msg}")

        # 找到实际下载的文件
        filenames = result.stdout.strip().split("\n")
        for fname in reversed(filenames):
            if os.path.exists(fname):
                logger.info(f"已下载: {fname}")
                return fname

        # 如果 stdout 没给路径，自己找
        for f in os.listdir(output_dir):
            fpath = os.path.join(output_dir, f)
            if os.path.isfile(fpath) and not f.endswith(".part"):
                return fpath

        raise FileNotFoundError(f"下载后找不到文件，目录: {output_dir}")

    except subprocess.TimeoutExpired:
        raise RuntimeError("下载超时（5分钟）")
    except Exception:
        if tmp_dir:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def list_formats(url: str) -> list:
    """列出可用的视频/音频格式"""
    cmd = [YTDLP, "-F", "--no-warnings", url]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"查询格式失败: {result.stderr[:300]}")
    return result.stdout.strip().split("\n")