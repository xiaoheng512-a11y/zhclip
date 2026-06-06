"""
zhclip.transcribe - 核心转写模块
纯 CPU，使用 sherpa-onnx + SenseVoice 支持中文/中英混合

用法:
    from zhclip.transcribe import transcribe_file
    result = transcribe_file("meeting.mp3")
    # 返回: { "text", "segments": [{ "text", "start", "end", "translated" }], "duration", "elapsed", "language" }

路径配置:
    ZHCLIP_DATA 环境变量指定数据目录（默认 E:/Programs/zhclip/data）
"""

import os
import sys
import json
import re
import time
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger("zhclip")

# ── 数据目录配置 ────────────────────────────────────
def _get_data_dir() -> Path:
    env = os.environ.get("ZHCLIP_DATA")
    if env:
        return Path(env)
    return Path("E:/Programs/zhclip/data")

DATA_DIR = _get_data_dir()
MODEL_CACHE = DATA_DIR / "models"
TEMP_DIR = DATA_DIR / "tmp"
CACHE_DIR = DATA_DIR / "downloads"


# ── ffmpeg 查找 ─────────────────────────────────────
def _find_ffmpeg() -> str:
    candidates = ["ffmpeg", "ffmpeg.exe", r"C:/tools/bin/ffmpeg.exe",
                   str(Path.home() / "tools" / "bin" / "ffmpeg.exe")]
    for c in candidates:
        try:
            subprocess.run([c, "-version"], capture_output=True, timeout=5)
            return c
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    raise RuntimeError("找不到 ffmpeg。请下载并放在 PATH 中")

FFMPEG = _find_ffmpeg()


# ── 模型配置 ─────────────────────────────────────────
MODEL_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
             "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2")
MODEL_DIR_NAME = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"


def _get_model_path() -> Path:
    model_dir = MODEL_CACHE / MODEL_DIR_NAME
    if not model_dir.exists():
        logger.info("首次运行，下载语音模型 (~150MB)...")
        MODEL_CACHE.mkdir(parents=True, exist_ok=True)
        archive_path = MODEL_CACHE / f"{MODEL_DIR_NAME}.tar.bz2"
        import urllib.request
        def reporthook(b, bs, ts):
            sys.stderr.write(f"\r  下载中: {b*bs/1024/1024:.0f}/{ts/1024/1024:.0f} MB")
            sys.stderr.flush()
        urllib.request.urlretrieve(MODEL_URL, archive_path, reporthook)
        print()
        logger.info("解压模型中...")
        import tarfile
        with tarfile.open(archive_path, "rbz2") as tar:
            tar.extractall(path=MODEL_CACHE)
        archive_path.unlink()
        assert model_dir.exists(), f"模型解压失败: {model_dir}"
    return model_dir


def _init_recognizer(model_path: Path, language: str = "auto", use_itn: bool = True):
    try:
        import sherpa_onnx
    except ImportError:
        raise ImportError("请先安装 sherpa-onnx: pip install sherpa-onnx")

    encoder = str(model_path / "model.onnx")
    tokens = str(model_path / "tokens.txt")

    int8_path = model_path / "model.int8.onnx"
    if int8_path.exists():
        encoder = str(int8_path)
        logger.info("  使用 INT8 量化模型（省内存）")

    if not os.path.exists(encoder):
        raise FileNotFoundError(f"模型文件不存在: {encoder}")
    if not os.path.exists(tokens):
        raise FileNotFoundError(f"词表文件不存在: {tokens}")

    lang_map = {"auto": "", "zh": "zh", "zh-en": "zh", "en": "en",
                "ja": "ja", "ko": "ko", "yue": "yue"}
    lang = lang_map.get(language, "")

    return sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=encoder, tokens=tokens, num_threads=4,
        provider="cpu", language=lang, use_itn=use_itn,
    )


def _extract_audio(input_path: str, output_path: str, sample_rate: int = 16000) -> str:
    logger.info(f"提取音频: {input_path}")
    if input_path.lower().endswith(".wav"):
        try:
            r = subprocess.run([FFMPEG, "-i", input_path, "-f", "null", "-"],
                               capture_output=True, text=True, timeout=30)
            if "pcm_s16le" in r.stderr and "16000 Hz" in r.stderr and "mono" in r.stderr:
                logger.info("  已经是 16kHz mono WAV，跳过转码")
                return input_path
        except Exception:
            pass
    cmd = [FFMPEG, "-y", "-i", input_path, "-vn", "-acodec", "pcm_s16le",
           "-ar", str(sample_rate), "-ac", "1", "-loglevel", "error", output_path]
    subprocess.run(cmd, check=True, timeout=300)
    logger.info(f"  输出: {output_path}")
    return output_path


# ── 翻译 ──────────────────────────────────────────
_TRANSLATOR_CACHE = {}

def translate_text(text: str, source: str = "en", target: str = "zh-CN") -> str:
    """翻译文本，带缓存和超时"""
    if not text or not text.strip():
        return ""
    cache_key = f"{source}:{target}:{text}"
    if cache_key in _TRANSLATOR_CACHE:
        return _TRANSLATOR_CACHE[cache_key]

    try:
        from deep_translator import GoogleTranslator
        import concurrent.futures

        def _do_translate():
            t = GoogleTranslator(source=source, target=target)
            return t.translate(text)

        with concurrent.futures.ThreadPoolExecutor() as ex:
            fut = ex.submit(_do_translate)
            result = fut.result(timeout=8)
            _TRANSLATOR_CACHE[cache_key] = result
            return result
    except concurrent.futures.TimeoutError:
        logger.warning(f"  翻译超时（8s），跳过: {text[:30]}...")
        return ""
    except Exception as e:
        logger.warning(f"  翻译失败: {type(e).__name__}: {str(e)[:50]}")
        return ""


# ── 段落分割 ──────────────────────────────────────
def _group_into_segments(timed_tokens: list) -> list:
    """将 (时间戳, 单词) 列表分组为句子段落

    timed_tokens: [(start_time, end_time, word), ...]
    返回: [{"text": "...", "start": 0.0, "end": 3.5}, ...]
    """
    if not timed_tokens:
        return []

    SENTENCE_ENDERS = {".", "!", "?", "。", "！", "？", "\n"}
    MIN_GAP = 1.0  # 超过1秒静音视为新段
    MAX_SEGMENT_WORDS = 50  # 一段最多50词

    segments = []
    current_words = []
    current_start = timed_tokens[0][0]

    for i, (st, et, word) in enumerate(timed_tokens):
        current_words.append(word)

        # 判断是否应该切段
        is_end = word[-1] in SENTENCE_ENDERS if word else False
        has_long_gap = False
        if i < len(timed_tokens) - 1:
            next_st = timed_tokens[i + 1][0]
            has_long_gap = (next_st - et) > MIN_GAP

        too_long = len(current_words) >= MAX_SEGMENT_WORDS

        if is_end or has_long_gap or too_long or i == len(timed_tokens) - 1:
            text = " ".join(current_words).strip()
            # 清理多余空格（标点前）
            text = re.sub(r'\s+([,.:;!?])', r'\1', text)
            text = re.sub(r'\s+', ' ', text)
            if text:
                segments.append({
                    "text": text,
                    "start": round(current_start, 1),
                    "end": round(et, 1),
                })
            current_words = []
            current_start = next_st if i < len(timed_tokens) - 1 else et

    return segments


# ── 主转写函数 ────────────────────────────────────
def transcribe_file(
    input_path: str,
    language: str = "auto",
    use_itn: bool = True,
    model_path: Optional[str] = None,
    translate: bool = False,
) -> dict:
    """
    转写一个音频/视频文件，返回带时间戳的分段结果。

    参数:
        translate: 是否翻译为中文
    返回:
        { "text", "segments": [{ "text", "start", "end", "translated" }],
          "duration", "elapsed", "language" }
    """
    t0 = time.time()
    mp = Path(model_path) if model_path else _get_model_path()

    logger.info("初始化识别器...")
    recognizer = _init_recognizer(mp, language=language, use_itn=use_itn)

    # 提取音频
    wav_path = str(Path(input_path).with_suffix(".zhclip_tmp.wav"))
    try:
        wav_path = _extract_audio(input_path, wav_path, sample_rate=16000)

        logger.info("读取音频...")
        import wave
        with wave.open(wav_path, "rb") as f:
            assert f.getnchannels() == 1, "只支持单声道"
            assert f.getsampwidth() == 2, "只支持 16-bit"
            samples_bytes = f.readframes(f.getnframes())
            duration = f.getnframes() / f.getframerate()

        import numpy as np
        samples = np.frombuffer(samples_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        logger.info(f"  音频长度: {duration:.1f}s")

        # 分块处理（避免 OOM）
        CHUNK_SIZE = 30 * 16000  # 30秒
        all_timed_tokens = []
        total_chunks = (len(samples) + CHUNK_SIZE - 1) // CHUNK_SIZE

        for chunk_idx in range(total_chunks):
            start_sample = chunk_idx * CHUNK_SIZE
            end_sample = min(start_sample + CHUNK_SIZE, len(samples))
            chunk = samples[start_sample:end_sample]
            chunk_offset = start_sample / 16000  # 秒

            logger.info(f"  处理第 {chunk_idx+1}/{total_chunks} 块...")
            stream = recognizer.create_stream()
            stream.accept_waveform(16000, chunk)
            recognizer.decode_streams([stream])
            result = stream.result

            # 提取单词和时间戳
            tokens = result.tokens if hasattr(result, 'tokens') else []
            timestamps = result.timestamps if hasattr(result, 'timestamps') else []

            if tokens and timestamps:
                # timestamps 长度可能与 tokens 不一致，安全处理
                for i, token in enumerate(tokens):
                    if i < len(timestamps):
                        ts = timestamps[i] + chunk_offset
                        # 估算单词结束时间（下一个时间戳或+0.3s）
                        next_ts = timestamps[i+1] + chunk_offset if i+1 < len(timestamps) else ts + 0.3
                        all_timed_tokens.append((ts, next_ts, token.strip()))
                    else:
                        all_timed_tokens.append((chunk_offset, chunk_offset + 0.3, token.strip()))

        # 分为段落
        segments = _group_into_segments(all_timed_tokens)
        full_text = " ".join(s["text"] for s in segments)

        # 检测语言
        detected_lang = getattr(result, 'lang', language) if 'result' in dir() else language
        detected_lang = detected_lang.replace("<|", "").replace("|>", "") if detected_lang else language

        # 翻译（如果需要）
        if translate and detected_lang != "zh":
            logger.info("翻译为中文...")
            for seg in segments:
                seg["translated"] = translate_text(seg["text"], source=detected_lang)
        elif translate:
            # 已经是中文
            for seg in segments:
                seg["translated"] = seg["text"]

    finally:
        tmp_wav = Path(wav_path)
        if tmp_wav.exists() and "_zhclip_tmp" in str(tmp_wav):
            tmp_wav.unlink()

    elapsed = time.time() - t0
    logger.info(f"转写完成，耗时 {elapsed:.1f}s")

    return {
        "text": full_text,
        "segments": segments,
        "duration": round(duration, 1),
        "elapsed": round(elapsed, 1),
        "language": detected_lang if 'detected_lang' in dir() else language,
    }


def _extract_video_id(url: str) -> Optional[str]:
    patterns = [r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})",
                r"(?:embed/|shorts/)([a-zA-Z0-9_-]{11})"]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def transcribe_url(
    url: str,
    language: str = "auto",
    model_path: Optional[str] = None,
    translate: bool = False,
) -> dict:
    """
    下载并转写在线视频，带缓存。支持翻译。
    """
    import sys
    print("[DEBUG] transcribe_url start", flush=True)
    from zhclip.download import YTDLP
    print("[DEBUG] YTDLP imported", flush=True)

    video_id = _extract_video_id(url)
    print(f"[DEBUG] video_id={video_id}", flush=True)
    cache_key = video_id or str(hash(url))

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[DEBUG] cache_key={cache_key}", flush=True)

    # ── 检查缓存：完整转写结果 ──
    result_json = CACHE_DIR / f"{cache_key}.json"
    print(f"[DEBUG] checking cache: {result_json}", flush=True)
    if result_json.exists():
        print(f"[DEBUG] cache exists!", flush=True)
        with open(result_json, "r", encoding="utf-8") as f:
            cached = json.load(f)
        # 向后兼容
        if "segments" not in cached or not cached["segments"]:
            text = cached.get("text", "")
            if text:
                cached["segments"] = [{"text": text, "start": 0, "end": cached.get("duration", 0)}]
        # 如果请求是 auto 或语言匹配，命中缓存
        if language == "auto" or cached.get("language") == language:
            print(f"[DEBUG] cache hit (lang={cached.get('language')}, requested={language}), returning", flush=True)
            if translate and not cached.get("segments", [{}])[0].get("translated"):
                logger.info("补翻译...")
                for seg in cached["segments"]:
                    seg["translated"] = translate_text(seg["text"])
                with open(result_json, "w", encoding="utf-8") as f:
                    json.dump(cached, f, ensure_ascii=False, indent=2)
            return cached
        print(f"[DEBUG] language mismatch: cached={cached.get('language')}, requested={language}", flush=True)

    # ── 检查缓存：已下载的音频文件 ──
    cached_audio = CACHE_DIR / f"{cache_key}.webm"
    need_download = not cached_audio.exists()

    if need_download:
        logger.info(f"下载视频: {url}")
        tmp_dir = tempfile.mkdtemp(dir=str(TEMP_DIR))
        output_template = os.path.join(tmp_dir, "%(title)s.%(ext)s")
        try:
            cmd = [YTDLP, "-f", "bestaudio/best", "-o", output_template,
                   "--no-playlist", "--print", "after_move:filename",
                   "--no-warnings", url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                raise RuntimeError(f"yt-dlp 失败: {result.stderr[:500]}")

            output_file = result.stdout.strip().split("\n")[-1]
            if not os.path.exists(output_file):
                for f in os.listdir(tmp_dir):
                    fpath = os.path.join(tmp_dir, f)
                    if os.path.isfile(fpath) and not f.endswith(".part"):
                        output_file = fpath
                        break
                else:
                    raise FileNotFoundError(f"下载后找不到音频文件，目录: {tmp_dir}")

            import shutil
            shutil.copy2(output_file, cached_audio)
            output_file = str(cached_audio)
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
    else:
        logger.info(f"使用缓存音频: {cached_audio}")
        output_file = str(cached_audio)

    # ── 转写 ──
    logger.info("开始转写...")
    result = transcribe_file(output_file, language=language, model_path=model_path,
                             translate=translate)
    result["source_url"] = url

    # ── 缓存 ──
    with open(result_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(sys.argv) < 2:
        print("用法: python -m zhclip.transcribe <音频文件或URL> [--translate]")
        sys.exit(1)

    translate = "--translate" in sys.argv
    arg = sys.argv[1]
    if arg.startswith(("http://", "https://")):
        r = transcribe_url(arg, translate=translate)
    else:
        r = transcribe_file(arg, translate=translate)

    print("\n" + "=" * 50)
    for seg in r.get("segments", []):
        ts = f"[{seg['start']:.1f}s - {seg['end']:.1f}s]"
        print(f"{ts} {seg['text']}")
        if seg.get("translated"):
            print(f"{' ' * len(ts)} {seg['translated']}")
        print()
    print(f"时长: {r['duration']}s | 处理: {r['elapsed']}s")
