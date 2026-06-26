import html
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path


SUBTITLE_EXTENSIONS = (".srt", ".vtt", ".ass", ".ssa")
TIME_LINE_RE = re.compile(r"(.+?)\s*-->\s*(.+)")
ASS_TAG_RE = re.compile(r"\{[^}]*\}")
HTML_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class TextSegment:
    start: float
    end: float
    text: str
    source: str = ""


def format_timestamp(seconds):
    seconds = max(0.0, float(seconds or 0.0))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    whole_seconds = int(seconds % 60)
    milliseconds = int(round((seconds - int(seconds)) * 1000))
    if milliseconds == 1000:
        whole_seconds += 1
        milliseconds = 0
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


def format_time_range(segment):
    return f"{format_timestamp(segment.start)}-{format_timestamp(segment.end)}"


def read_text_with_fallback(path):
    encodings = ("utf-8-sig", "utf-8", "gb18030")
    last_error = None
    for encoding in encodings:
        try:
            with open(path, "r", encoding=encoding) as handle:
                return handle.read()
        except UnicodeDecodeError as error:
            last_error = error
    raise UnicodeDecodeError(
        "unknown",
        b"",
        0,
        1,
        f"Cannot decode subtitle file with {', '.join(encodings)}: {last_error}",
    )


def parse_timestamp(value):
    value = value.strip()
    value = value.split()[0]
    match = re.match(r"(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:[,.](\d{1,3}))?", value)
    if not match:
        raise ValueError(f"Invalid timestamp: {value}")

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    fraction = (match.group(4) or "0").ljust(3, "0")[:3]
    milliseconds = int(fraction)
    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000


def clean_subtitle_text(text):
    text = html.unescape(text)
    text = ASS_TAG_RE.sub("", text)
    text = HTML_TAG_RE.sub("", text)
    text = text.replace("\\N", " ").replace("\\n", " ").replace("\\h", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_srt_or_vtt(path, content):
    segments = []
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", content)
    for block in blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines or lines[0].upper() == "WEBVTT":
            continue

        time_index = None
        for index, line in enumerate(lines):
            if "-->" in line:
                time_index = index
                break
        if time_index is None:
            continue

        match = TIME_LINE_RE.match(lines[time_index])
        if not match:
            continue

        start = parse_timestamp(match.group(1))
        end = parse_timestamp(match.group(2))
        text = clean_subtitle_text(" ".join(lines[time_index + 1 :]))
        if text:
            segments.append(TextSegment(start, end, text, source=str(path)))
    return segments


def parse_ass_or_ssa(path, content):
    segments = []
    in_events = False
    fields = []

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("["):
            in_events = line.lower() == "[events]"
            continue
        if not in_events:
            continue
        if line.lower().startswith("format:"):
            fields = [part.strip().lower() for part in line.split(":", 1)[1].split(",")]
            continue
        if not line.lower().startswith("dialogue:"):
            continue

        payload = line.split(":", 1)[1].lstrip()
        if fields:
            parts = payload.split(",", max(0, len(fields) - 1))
            if len(parts) < len(fields):
                continue
            field_map = {name: parts[index] for index, name in enumerate(fields)}
            start_value = field_map.get("start")
            end_value = field_map.get("end")
            text_value = field_map.get("text", "")
        else:
            parts = payload.split(",", 9)
            if len(parts) < 10:
                continue
            start_value = parts[1]
            end_value = parts[2]
            text_value = parts[9]

        if not start_value or not end_value:
            continue
        text = clean_subtitle_text(text_value)
        if text:
            segments.append(
                TextSegment(parse_timestamp(start_value), parse_timestamp(end_value), text, source=str(path))
            )
    return segments


def parse_subtitle_file(path):
    subtitle_path = Path(path)
    if not subtitle_path.exists():
        raise FileNotFoundError(f"找不到字幕文件: {subtitle_path}")

    content = read_text_with_fallback(subtitle_path)
    suffix = subtitle_path.suffix.lower()
    if suffix in {".srt", ".vtt"}:
        segments = parse_srt_or_vtt(subtitle_path, content)
    elif suffix in {".ass", ".ssa"}:
        segments = parse_ass_or_ssa(subtitle_path, content)
    else:
        raise ValueError(f"不支持的字幕格式: {suffix}")

    if not segments:
        raise RuntimeError(f"字幕文件没有解析出有效文本: {subtitle_path}")
    return segments


def find_sidecar_subtitle(video_path):
    video = Path(video_path)
    for extension in SUBTITLE_EXTENSIONS:
        candidate = video.with_suffix(extension)
        if candidate.exists():
            return str(candidate)
    return None


def normalize_for_compare(text):
    normalized = unicodedata.normalize("NFKC", text or "").lower()
    kept = []
    for char in normalized:
        category = unicodedata.category(char)
        if category.startswith("P") or category.startswith("S") or char.isspace():
            continue
        kept.append(char)
    return "".join(kept)


def text_similarity(left, right):
    left_norm = normalize_for_compare(left)
    right_norm = normalize_for_compare(right)
    if not left_norm and not right_norm:
        return 1.0
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def segment_center(segment):
    return (segment.start + segment.end) / 2


def shifted_segment(segment, offset):
    return TextSegment(segment.start + offset, segment.end + offset, segment.text, segment.source)


def time_score(primary, candidate):
    primary_duration = max(0.1, primary.end - primary.start)
    candidate_duration = max(0.1, candidate.end - candidate.start)
    overlap = max(0.0, min(primary.end, candidate.end) - max(primary.start, candidate.start))
    if overlap:
        return min(1.0, overlap / min(primary_duration, candidate_duration))

    center_gap = abs(segment_center(primary) - segment_center(candidate))
    if center_gap <= 2.0:
        return max(0.0, 1.0 - center_gap / 2.0)
    return 0.0


def find_best_match(primary, candidates, candidate_offset=0.0):
    best = None
    for index, candidate in enumerate(candidates):
        adjusted = shifted_segment(candidate, candidate_offset)
        similarity = text_similarity(primary.text, candidate.text)
        timing = time_score(primary, adjusted)
        score = similarity * 0.72 + timing * 0.28
        time_delta = segment_center(adjusted) - segment_center(primary)
        if best is None or score > best["score"]:
            best = {
                "index": index,
                "segment": candidate,
                "adjusted": adjusted,
                "similarity": similarity,
                "time_score": timing,
                "time_delta": time_delta,
                "score": score,
            }
    return best


def estimate_subtitle_offset(speech_segments, subtitle_segments):
    if not speech_segments or not subtitle_segments:
        return 0.0

    offsets = [value / 2 for value in range(-6, 7)]
    best_offset = 0.0
    best_score = -1.0
    sample = speech_segments[:80]

    for offset in offsets:
        scores = []
        for speech in sample:
            match = find_best_match(speech, subtitle_segments, candidate_offset=offset)
            if match:
                scores.append(match["score"])
        score = sum(scores) / len(scores) if scores else 0.0
        if score > best_score:
            best_score = score
            best_offset = offset

    return 0.0 if abs(best_offset) < 0.25 else best_offset


def table_text(value, limit=80):
    value = re.sub(r"\s+", " ", value or "").strip()
    value = value.replace("|", "\\|")
    if len(value) > limit:
        return value[: limit - 1] + "…"
    return value


def percent(value):
    return f"{round(value * 100)}%"


def build_subtitle_markdown(video_path, subtitle_segments, subtitle_source):
    if not subtitle_segments:
        raise RuntimeError("字幕识别结果为空。")

    source = os.path.abspath(video_path)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# 字幕识别稿",
        "",
        f"- Source video: `{source}`",
        f"- Subtitle source: `{subtitle_source}`",
        f"- Generated at: {generated_at}",
        "",
        "## 字幕内容",
        "",
    ]
    for segment in subtitle_segments:
        lines.append(f"- [{format_time_range(segment)}] {segment.text}")
    lines.append("")
    return "\n".join(lines)


def build_subtitle_comparison_report(
    video_path,
    speech_segments,
    subtitle_segments,
    transcript_path,
    subtitle_source,
    similarity_threshold=0.72,
):
    if not speech_segments:
        raise RuntimeError("语音转写结果为空，无法进行字幕核对。")
    if not subtitle_segments:
        raise RuntimeError("字幕识别结果为空，无法进行字幕核对。")

    offset = estimate_subtitle_offset(speech_segments, subtitle_segments)
    issues = []
    matched_subtitle_indexes = set()
    text_diff_count = 0
    missing_subtitle_count = 0
    missing_speech_count = 0
    timing_count = 0

    for speech in speech_segments:
        match = find_best_match(speech, subtitle_segments, candidate_offset=offset)
        if not match or (match["similarity"] < 0.45 and match["time_score"] < 0.35):
            missing_subtitle_count += 1
            issues.append(
                [
                    format_time_range(speech),
                    "语音有，字幕疑似缺失",
                    speech.text,
                    "",
                    "0%",
                    "检查字幕是否漏配或 OCR 未识别。",
                ]
            )
            continue

        matched_subtitle_indexes.add(match["index"])
        subtitle = match["segment"]
        if match["similarity"] < similarity_threshold:
            text_diff_count += 1
            issues.append(
                [
                    format_time_range(speech),
                    "文字不一致",
                    speech.text,
                    subtitle.text,
                    percent(match["similarity"]),
                    "同一时间段语音和字幕表达不一致。",
                ]
            )
        elif abs(match["time_delta"]) > 1.2 and match["similarity"] >= similarity_threshold:
            timing_count += 1
            issues.append(
                [
                    format_time_range(speech),
                    "时间可能未同步",
                    speech.text,
                    subtitle.text,
                    percent(match["similarity"]),
                    f"字幕相对语音约 {match['time_delta']:+.1f}s。",
                ]
            )

    for index, subtitle in enumerate(subtitle_segments):
        if index in matched_subtitle_indexes:
            continue
        adjusted_subtitle = shifted_segment(subtitle, offset)
        match = find_best_match(adjusted_subtitle, speech_segments, candidate_offset=0.0)
        if not match or (match["similarity"] < 0.45 and match["time_score"] < 0.35):
            missing_speech_count += 1
            issues.append(
                [
                    format_time_range(adjusted_subtitle),
                    "字幕有，语音疑似缺失",
                    "",
                    subtitle.text,
                    "0%",
                    "可能是画面标题、贴片文字、OCR 误识别，或语音转写漏听。",
                ]
            )

    source = os.path.abspath(video_path)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# 字幕双向核对报告",
        "",
        f"- Source video: `{source}`",
        f"- Speech transcript: `{os.path.abspath(transcript_path)}`",
        f"- Subtitle source: `{subtitle_source}`",
        f"- Generated at: {generated_at}",
        f"- Estimated subtitle offset: `{offset:+.1f}s` （核对时按 `字幕时间 + offset` 对齐语音）",
        f"- Similarity threshold: `{similarity_threshold:.2f}`",
        "",
        "## 核对摘要",
        "",
        f"- 语音片段数：{len(speech_segments)}",
        f"- 字幕片段数：{len(subtitle_segments)}",
        f"- 文字不一致：{text_diff_count}",
        f"- 语音有但字幕疑似缺失：{missing_subtitle_count}",
        f"- 字幕有但语音疑似缺失：{missing_speech_count}",
        f"- 时间可能未同步：{timing_count}",
        "",
        "## 需要人工关注的问题",
        "",
    ]

    if not issues:
        lines.append("未发现明显的字幕/语音不一致问题。")
        lines.append("")
        return "\n".join(lines)

    lines.extend(
        [
            "| 时间段 | 问题类型 | 语音转写 | 字幕文本 | 相似度 | 备注 |",
            "|---|---|---|---|---|---|",
        ]
    )
    for issue in issues:
        time_range, issue_type, speech_text, subtitle_text, similarity, note = issue
        lines.append(
            "| "
            + " | ".join(
                [
                    table_text(time_range, 40),
                    table_text(issue_type, 30),
                    table_text(speech_text),
                    table_text(subtitle_text),
                    table_text(similarity, 10),
                    table_text(note),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def load_rapid_ocr():
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        try:
            from rapidocr import RapidOCR
        except ImportError as error:
            raise RuntimeError(
                "缺少硬字幕 OCR 依赖。请安装 requirements.txt，或单独安装 rapidocr-onnxruntime、Pillow、numpy。"
            ) from error
    return RapidOCR()


def crop_subtitle_area(image, area):
    width, height = image.size
    if area == "full":
        return image
    if area == "bottom":
        return image.crop((0, int(height * 0.55), width, height))
    if area == "lower-third":
        return image.crop((0, int(height * 0.62), width, height))
    raise ValueError(f"不支持的字幕识别区域: {area}")


def upscale_image(image):
    width, height = image.size
    if width >= 1600:
        return image
    scale = 2
    try:
        from PIL import Image as PILImage

        resampling = PILImage.Resampling.LANCZOS
    except Exception:
        resampling = 1
    return image.resize((width * scale, height * scale), resampling)


def extract_text_from_ocr_result(result, min_confidence):
    if isinstance(result, tuple):
        result = result[0]
    if not result:
        return ""

    text_parts = []
    for item in result:
        if len(item) < 3:
            continue
        text = str(item[1]).strip()
        try:
            score = float(item[2])
        except (TypeError, ValueError):
            score = 0.0
        if text and score >= min_confidence:
            text_parts.append(text)
    return clean_subtitle_text(" ".join(text_parts))


def ocr_video_subtitles(video_path, sample_interval=1.0, area="bottom", min_confidence=0.45):
    try:
        import av
        import numpy as np
    except ImportError as error:
        raise RuntimeError("缺少视频解码或图像处理依赖，请先安装 requirements.txt。") from error

    if sample_interval <= 0:
        raise ValueError("--ocr-sample-interval 必须大于 0。")

    engine = load_rapid_ocr()
    segments = []
    current_text = ""
    current_key = ""
    current_start = None
    current_end = None
    next_sample_time = 0.0

    print(f"[PROGRESS] OCR hard subtitles every {sample_interval:.2f}s from {area} area...")
    container = av.open(video_path)
    try:
        video_stream = next((stream for stream in container.streams if stream.type == "video"), None)
        if video_stream is None:
            raise RuntimeError("视频中没有可识别的视频轨道，无法 OCR 字幕。")

        with tempfile.TemporaryDirectory(prefix="subtitle-ocr-") as _:
            for frame in container.decode(video_stream):
                frame_time = float(frame.pts * frame.time_base) if frame.pts is not None else next_sample_time
                if frame_time + 0.001 < next_sample_time:
                    continue
                next_sample_time = frame_time + sample_interval

                image = frame.to_image().convert("RGB")
                image = upscale_image(crop_subtitle_area(image, area))
                text = extract_text_from_ocr_result(engine(np.array(image)), min_confidence)
                key = normalize_for_compare(text)

                if key == current_key:
                    if current_key:
                        current_end = frame_time + sample_interval
                    continue

                if current_key and current_text and current_start is not None:
                    segments.append(TextSegment(current_start, current_end or frame_time, current_text, "hard-subtitle-ocr"))

                current_text = text
                current_key = key
                current_start = frame_time if key else None
                current_end = frame_time + sample_interval if key else None
                print(".", end="", flush=True)

        if current_key and current_text and current_start is not None:
            segments.append(TextSegment(current_start, current_end or current_start + sample_interval, current_text, "hard-subtitle-ocr"))
    finally:
        container.close()

    if segments:
        print()
    if not segments:
        raise RuntimeError("硬字幕 OCR 没有识别到字幕文本；可尝试 --subtitle-area full 或提供外部字幕文件。")
    return segments
