import hashlib
import io
import math
import re
import tempfile
import zipfile
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw


MAX_VIDEO_FILE_SIZE_BYTES = 25 * 1024 * 1024
MIN_VIDEO_DURATION_SECONDS = 1
MAX_VIDEO_DURATION_SECONDS = 60
MAX_SAMPLED_FRAMES = 12
SUPPORTED_VIDEO_EXTENSIONS = {".mp4"}
SUPPORTED_VIDEO_MIME_TYPES = {"video/mp4", "application/octet-stream", ""}


def validate_uploaded_video(uploaded_file):
    errors = []
    warnings = []
    if uploaded_file is None:
        errors.append("No uploaded video file was provided.")
        return False, errors, warnings

    original_filename = getattr(uploaded_file, "name", "")
    extension = Path(original_filename).suffix.lower()
    if extension not in SUPPORTED_VIDEO_EXTENSIONS:
        errors.append("Only MP4 video files are supported in Version 1.7.")

    mime_type = getattr(uploaded_file, "type", "")
    if mime_type not in SUPPORTED_VIDEO_MIME_TYPES:
        warnings.append(f"Unexpected MIME type: {mime_type or 'unknown'}")

    file_size = uploaded_file_size(uploaded_file)
    if file_size <= 0:
        errors.append("Uploaded video file is empty.")
    if file_size > MAX_VIDEO_FILE_SIZE_BYTES:
        errors.append("Uploaded video file exceeds the 25 MB limit.")

    safe_filename = sanitize_filename(original_filename)
    if safe_filename != Path(original_filename).name:
        warnings.append("Filename was sanitized for temporary processing.")

    return not errors, errors, warnings


def save_uploaded_video_temporarily(uploaded_file, temp_dir):
    original_filename = getattr(uploaded_file, "name", "uploaded_video.mp4")
    safe_filename = sanitize_filename(original_filename)
    content = uploaded_file_bytes(uploaded_file)
    file_hash = hashlib.sha256(content).hexdigest()
    target_name = f"{file_hash[:12]}_{safe_filename}"
    target_path = Path(temp_dir) / target_name
    target_path.write_bytes(content)
    return {
        "path": target_path,
        "original_filename": original_filename,
        "safe_filename": target_name,
        "file_size_bytes": len(content),
        "file_hash": file_hash,
    }


def extract_video_metadata(video_path, file_info):
    metadata = {
        "original_filename": file_info["original_filename"],
        "safe_filename": file_info["safe_filename"],
        "file_size_bytes": file_info["file_size_bytes"],
        "file_hash": file_info["file_hash"],
        "duration_seconds": pd.NA,
        "width": pd.NA,
        "height": pd.NA,
        "aspect_ratio": pd.NA,
        "video_orientation": "unknown",
        "resolution_label": "unknown",
        "frame_rate": pd.NA,
        "estimated_frame_count": pd.NA,
        "video_codec": "unknown",
        "audio_track_present": False,
        "creation_timestamp": "",
        "processing_status": "failed",
        "processing_notes": "",
        "short_form_eligible": False,
    }
    notes = []
    try:
        reader = imageio.get_reader(str(video_path), "ffmpeg")
        raw_meta = reader.get_meta_data()
        reader.close()
    except Exception as exc:
        metadata["processing_status"] = "failed"
        metadata["processing_notes"] = f"Could not decode video metadata: {exc}"
        return metadata

    duration = safe_float(raw_meta.get("duration"))
    fps = safe_float(raw_meta.get("fps"))
    size = raw_meta.get("size") or raw_meta.get("source_size") or [None, None]
    width = safe_int(size[0]) if len(size) >= 2 else None
    height = safe_int(size[1]) if len(size) >= 2 else None

    if duration is None or duration <= 0:
        metadata["processing_status"] = "rejected"
        metadata["processing_notes"] = "Video duration is unavailable or zero."
        return metadata
    if duration < MIN_VIDEO_DURATION_SECONDS:
        metadata["processing_status"] = "rejected"
        metadata["processing_notes"] = "Video duration is below the 1 second minimum."
        return metadata
    if duration > MAX_VIDEO_DURATION_SECONDS:
        metadata["processing_status"] = "rejected"
        metadata["processing_notes"] = "Video duration exceeds the 60 second limit."
        return metadata

    frame_count = int(round(duration * fps)) if fps else pd.NA
    metadata.update(
        {
            "duration_seconds": round(duration, 3),
            "width": width if width is not None else pd.NA,
            "height": height if height is not None else pd.NA,
            "aspect_ratio": round(width / height, 4)
            if width and height
            else pd.NA,
            "video_orientation": video_orientation(width, height),
            "resolution_label": resolution_label(width, height),
            "frame_rate": round(fps, 3) if fps else pd.NA,
            "estimated_frame_count": frame_count,
            "video_codec": raw_meta.get("codec") or raw_meta.get("video_codec") or "unknown",
            "audio_track_present": bool(raw_meta.get("audio_codec")),
            "creation_timestamp": raw_meta.get("creation_time", ""),
            "processing_status": "success",
            "short_form_eligible": is_short_form_eligible(duration, width, height),
        }
    )

    if not metadata["audio_track_present"]:
        notes.append("No audio track detected.")
    if not metadata["creation_timestamp"]:
        notes.append("Creation timestamp unavailable.")
    if metadata["video_orientation"] == "horizontal":
        notes.append("Horizontal orientation may be less suitable for short-form feeds.")
    if width and height and min(width, height) < 360:
        notes.append("Low resolution video.")

    metadata["processing_notes"] = "; ".join(notes)
    return metadata


def sample_video_frames(video_path, metadata, temp_dir):
    if metadata.get("processing_status") not in {"success", "partial"}:
        return [], "Metadata failed; frame sampling skipped."

    duration = float(metadata["duration_seconds"])
    fps = safe_float(metadata.get("frame_rate")) or 1.0
    estimated_count = safe_int(metadata.get("estimated_frame_count"))
    timestamps = sample_timestamps(duration)
    frames = []
    notes = []

    try:
        reader = imageio.get_reader(str(video_path), "ffmpeg")
        for position, timestamp in enumerate(timestamps, start=1):
            frame_index = max(0, int(round(timestamp * fps)))
            if estimated_count:
                frame_index = min(frame_index, max(estimated_count - 1, 0))
            try:
                frame_array = reader.get_data(frame_index)
            except Exception as exc:
                notes.append(f"Could not read frame at {timestamp:.2f}s: {exc}")
                continue
            image = Image.fromarray(frame_array).convert("RGB")
            frame_path = Path(temp_dir) / f"sampled_frame_{position:02d}.png"
            image.save(frame_path)
            frames.append(
                {
                    "timestamp": round(timestamp, 3),
                    "frame_index": frame_index,
                    "path": frame_path,
                    "image": image,
                    "array": np.asarray(image),
                }
            )
        reader.close()
    except Exception as exc:
        return [], f"Could not sample frames: {exc}"

    if not frames:
        return [], "No readable frames were sampled."
    return frames[:MAX_SAMPLED_FRAMES], "; ".join(notes)


def analyze_sampled_frames(frames, metadata):
    if not frames:
        return {
            "sampled_frame_count": 0,
            "sampled_timestamps": "",
            "average_brightness": pd.NA,
            "average_contrast": pd.NA,
            "black_frame_count": 0,
            "duplicate_frame_count": 0,
            "estimated_scene_change_count": 0,
            "approximate_shot_frequency": pd.NA,
            "opening_frame_activity": "unknown",
            "visual_analysis_status": "failed",
            "visual_analysis_notes": "No sampled frames were available.",
        }

    brightness_values = []
    contrast_values = []
    black_frame_count = 0
    duplicate_frame_count = 0
    scene_change_count = 0
    previous_small = None
    previous_gray = None
    opening_diffs = []

    for index, frame in enumerate(frames):
        gray = frame["array"].astype("float32").mean(axis=2)
        brightness = float(gray.mean())
        contrast = float(gray.std())
        brightness_values.append(brightness)
        contrast_values.append(contrast)
        if brightness < 8:
            black_frame_count += 1

        small = np.asarray(frame["image"].resize((32, 32))).astype("float32")
        if previous_small is not None:
            diff = float(np.mean(np.abs(small - previous_small)))
            if diff < 2.0:
                duplicate_frame_count += 1
            if diff > 25.0:
                scene_change_count += 1
            if index <= 2:
                opening_diffs.append(diff)
        previous_small = small
        previous_gray = gray

    duration = safe_float(metadata.get("duration_seconds")) or 0
    shot_frequency = scene_change_count / duration if duration > 0 else pd.NA
    opening_activity = classify_opening_activity(opening_diffs)
    notes = []
    if black_frame_count:
        notes.append("Black or very dark sampled frames detected.")
    if duplicate_frame_count:
        notes.append("Duplicate or near-duplicate sampled frames detected.")
    if np.nanmean(contrast_values) < 10:
        notes.append("Low contrast sampled frames detected.")

    return {
        "sampled_frame_count": len(frames),
        "sampled_timestamps": "; ".join(
            f"{frame['timestamp']:.3f}" for frame in frames
        ),
        "average_brightness": round(float(np.mean(brightness_values)), 3),
        "average_contrast": round(float(np.mean(contrast_values)), 3),
        "black_frame_count": black_frame_count,
        "duplicate_frame_count": duplicate_frame_count,
        "estimated_scene_change_count": scene_change_count,
        "approximate_shot_frequency": round(float(shot_frequency), 4)
        if not pd.isna(shot_frequency)
        else pd.NA,
        "opening_frame_activity": opening_activity,
        "visual_analysis_status": "success",
        "visual_analysis_notes": "; ".join(notes),
    }


def build_contact_sheet(frames, output_path, thumb_width=180):
    if not frames:
        return None, b""
    thumbs = []
    for frame in frames:
        image = frame["image"].copy()
        ratio = thumb_width / image.width
        thumb_height = max(1, int(image.height * ratio))
        image.thumbnail((thumb_width, thumb_height))
        canvas = Image.new("RGB", (thumb_width, thumb_height + 24), "white")
        canvas.paste(image, ((thumb_width - image.width) // 2, 0))
        draw = ImageDraw.Draw(canvas)
        draw.text((6, thumb_height + 5), f"{frame['timestamp']:.2f}s", fill="black")
        thumbs.append(canvas)

    columns = min(4, len(thumbs))
    rows = math.ceil(len(thumbs) / columns)
    cell_width = thumb_width
    cell_height = max(thumb.height for thumb in thumbs)
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "white")
    for index, thumb in enumerate(thumbs):
        x = (index % columns) * cell_width
        y = (index // columns) * cell_height
        sheet.paste(thumb, (x, y))
    sheet.save(output_path)
    data = Path(output_path).read_bytes()
    return output_path, data


def build_sampled_frames_zip(frames):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, frame in enumerate(frames, start=1):
            archive.write(
                frame["path"],
                arcname=f"sampled_frame_{index:02d}_{frame['timestamp']:.2f}s.png",
            )
    return buffer.getvalue()


def build_uploaded_video_text_record(
    metadata,
    associated_product,
    title="",
    description="",
    transcript="",
    hashtags="",
    language="",
):
    product_id = associated_product.get("product_id", "") if associated_product else ""
    product_name = associated_product.get("product_name", "") if associated_product else ""
    category = associated_product.get("category", "") if associated_product else ""
    return pd.DataFrame(
        [
            {
                "video_id": metadata.get("file_hash", "")[:12] or "uploaded_video",
                "product_id": product_id,
                "product_name": product_name,
                "category": category,
                "platform": "Uploaded File",
                "title": title.strip() or filename_to_title(metadata.get("original_filename", "")),
                "description": description,
                "transcript": transcript,
                "hashtags": hashtags,
                "creator_name": "",
                "language": language,
                "content_format": "",
                "hook_type": "",
                "cta_present": pd.NA,
                "main_feature": "",
            }
        ]
    )


def build_processing_report(metadata, visual_features, association):
    row = {**metadata, **visual_features, **association}
    return pd.DataFrame([row])


def process_uploaded_video(
    uploaded_file,
    associated_product=None,
    title="",
    description="",
    transcript="",
    hashtags="",
    language="",
):
    valid, errors, warnings = validate_uploaded_video(uploaded_file)
    if not valid:
        metadata = rejected_metadata(uploaded_file, errors)
        association = association_record(associated_product)
        return {
            "metadata": metadata,
            "visual_features": analyze_sampled_frames([], metadata),
            "association": association,
            "text_record": build_uploaded_video_text_record(
                metadata,
                associated_product,
                title,
                description,
                transcript,
                hashtags,
                language,
            ),
            "contact_sheet_bytes": b"",
            "sampled_frames_zip_bytes": b"",
            "report": build_processing_report(
                metadata,
                analyze_sampled_frames([], metadata),
                association,
            ),
            "warnings": warnings,
            "errors": errors,
        }

    with tempfile.TemporaryDirectory() as temp_dir:
        file_info = save_uploaded_video_temporarily(uploaded_file, temp_dir)
        metadata = extract_video_metadata(file_info["path"], file_info)
        metadata_warnings = metadata_notes(metadata)
        warnings = warnings + metadata_warnings
        frames = []
        contact_sheet_bytes = b""
        frames_zip_bytes = b""
        frame_notes = ""
        if metadata["processing_status"] == "success":
            frames, frame_notes = sample_video_frames(
                file_info["path"],
                metadata,
                temp_dir,
            )
            if frame_notes:
                warnings.append(frame_notes)
            if not frames:
                metadata["processing_status"] = "failed"
                metadata["processing_notes"] = append_note(
                    metadata["processing_notes"],
                    "No readable frames were sampled.",
                )
            else:
                contact_sheet_path, contact_sheet_bytes = build_contact_sheet(
                    frames,
                    Path(temp_dir) / "contact_sheet.png",
                )
                frames_zip_bytes = build_sampled_frames_zip(frames)

        visual_features = analyze_sampled_frames(frames, metadata)
        visual_notes = visual_features.get("visual_analysis_notes", "")
        if visual_notes:
            warnings.append(visual_notes)
        association = association_record(associated_product)
        if association["association_status"] == "unassigned":
            warnings.append("No product association selected.")
        if not transcript.strip():
            warnings.append("No transcript supplied.")

        text_record = build_uploaded_video_text_record(
            metadata,
            associated_product,
            title,
            description,
            transcript,
            hashtags,
            language,
        )
        report = build_processing_report(metadata, visual_features, association)
        return {
            "metadata": metadata,
            "visual_features": visual_features,
            "association": association,
            "text_record": text_record,
            "contact_sheet_bytes": contact_sheet_bytes,
            "sampled_frames_zip_bytes": frames_zip_bytes,
            "report": report,
            "warnings": dedupe_preserve_order(warnings),
            "errors": [],
        }


def cleanup_temporary_video_files(_path=None):
    return True


def sample_timestamps(duration):
    candidates = [0.5, 1.5, 2.5]
    candidates += [duration * 0.25, duration * 0.5, duration * 0.75]
    candidates += [duration - 3, duration - 1]
    timestamps = dedupe_timestamps(
        [value for value in candidates if 0 <= value < duration],
        tolerance=0.2,
    )
    if len(timestamps) < MAX_SAMPLED_FRAMES:
        fallback_count = MAX_SAMPLED_FRAMES
        for index in range(fallback_count):
            value = (index + 0.5) * duration / fallback_count
            if not any(abs(value - existing) <= 0.2 for existing in timestamps):
                timestamps.append(round(value, 3))
            if len(timestamps) >= MAX_SAMPLED_FRAMES:
                break
    return sorted(timestamps[:MAX_SAMPLED_FRAMES])


def dedupe_timestamps(values, tolerance):
    result = []
    for value in sorted(values):
        if value < 0:
            continue
        if not any(abs(value - existing) <= tolerance for existing in result):
            result.append(round(value, 3))
    return result


def sanitize_filename(filename):
    basename = Path(filename or "uploaded_video.mp4").name
    stem = Path(basename).stem
    suffix = Path(basename).suffix.lower() or ".mp4"
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    if not safe_stem:
        safe_stem = "uploaded_video"
    return f"{safe_stem[:80]}{suffix}"


def uploaded_file_bytes(uploaded_file):
    if hasattr(uploaded_file, "getvalue"):
        return uploaded_file.getvalue()
    if hasattr(uploaded_file, "getbuffer"):
        return bytes(uploaded_file.getbuffer())
    position = uploaded_file.tell() if hasattr(uploaded_file, "tell") else None
    content = uploaded_file.read()
    if position is not None and hasattr(uploaded_file, "seek"):
        uploaded_file.seek(position)
    return content


def uploaded_file_size(uploaded_file):
    size = getattr(uploaded_file, "size", None)
    if size is not None:
        return int(size)
    return len(uploaded_file_bytes(uploaded_file))


def video_orientation(width, height):
    if not width or not height:
        return "unknown"
    if width == height:
        return "square"
    return "vertical" if height > width else "horizontal"


def resolution_label(width, height):
    if not width or not height:
        return "unknown"
    short_side = min(width, height)
    long_side = max(width, height)
    if long_side >= 1920 or short_side >= 1080:
        return "1080p"
    if long_side >= 1280 or short_side >= 720:
        return "720p"
    if short_side < 360:
        return "low_resolution"
    return "standard_resolution"


def is_short_form_eligible(duration, width, height):
    return (
        duration <= MAX_VIDEO_DURATION_SECONDS
        and video_orientation(width, height) in {"vertical", "square"}
    )


def classify_opening_activity(opening_diffs):
    if not opening_diffs:
        return "unknown"
    average = float(np.mean(opening_diffs))
    if average > 35:
        return "high"
    if average > 10:
        return "medium"
    return "low"


def safe_float(value):
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def safe_int(value):
    try:
        if value is None or pd.isna(value):
            return None
        return int(value)
    except Exception:
        return None


def filename_to_title(filename):
    stem = Path(filename or "uploaded video").stem
    return " ".join(re.sub(r"[_-]+", " ", stem).split())


def association_record(product):
    if product:
        return {
            "associated_product_id": product.get("product_id", ""),
            "associated_product_name": product.get("product_name", ""),
            "association_method": "manual_dropdown",
            "association_status": "associated",
        }
    return {
        "associated_product_id": "",
        "associated_product_name": "",
        "association_method": "unassigned",
        "association_status": "unassigned",
    }


def rejected_metadata(uploaded_file, errors):
    original = getattr(uploaded_file, "name", "") if uploaded_file else ""
    size = uploaded_file_size(uploaded_file) if uploaded_file else 0
    content = uploaded_file_bytes(uploaded_file) if uploaded_file else b""
    return {
        "original_filename": original,
        "safe_filename": sanitize_filename(original),
        "file_size_bytes": size,
        "file_hash": hashlib.sha256(content).hexdigest() if content else "",
        "duration_seconds": pd.NA,
        "width": pd.NA,
        "height": pd.NA,
        "aspect_ratio": pd.NA,
        "video_orientation": "unknown",
        "resolution_label": "unknown",
        "frame_rate": pd.NA,
        "estimated_frame_count": pd.NA,
        "video_codec": "unknown",
        "audio_track_present": False,
        "creation_timestamp": "",
        "processing_status": "rejected",
        "processing_notes": "; ".join(errors),
        "short_form_eligible": False,
    }


def metadata_notes(metadata):
    notes = []
    text = metadata.get("processing_notes", "")
    if text:
        notes.extend([note.strip() for note in text.split(";") if note.strip()])
    return notes


def append_note(existing, note):
    return "; ".join(part for part in [existing, note] if part)


def dedupe_preserve_order(values):
    result = []
    seen = set()
    for value in values:
        if not value:
            continue
        for part in str(value).split(";"):
            cleaned = part.strip()
            if cleaned and cleaned not in seen:
                result.append(cleaned)
                seen.add(cleaned)
    return result
