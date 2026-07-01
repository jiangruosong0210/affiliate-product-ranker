import hashlib
import json
import re
import tempfile
from pathlib import Path

from video_generation_provider import (
    ACTIVE_VIDEO_STATUSES,
    MockVideoGenerationProvider,
    VideoGenerationError,
    VideoGenerationRequest,
)


SAFE_FILENAME_PATTERN = re.compile(r"[^a-zA-Z0-9._-]+")
VIDEO_OUTPUT_ROOT = Path(tempfile.gettempdir()) / "affiliate_ranker_video_outputs"


def safe_filename(value, default="video"):
    text = SAFE_FILENAME_PATTERN.sub("-", str(value).strip().lower())
    text = text.strip(".-")
    return text[:80] or default


def get_video_output_dir():
    VIDEO_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    return VIDEO_OUTPUT_ROOT


def is_valid_mp4(path):
    path = Path(path)
    if not path.exists() or path.stat().st_size <= 0:
        return False
    header = path.read_bytes()[:32]
    return b"ftyp" in header


def build_video_generation_request(
    creative_package,
    provider_name="Mock Video Provider",
    model_name="mock-placeholder-video-v1",
    prompt_override=None,
):
    payload = creative_package.get("provider_neutral_payload", {})
    prompts = creative_package.get("prompts", {})
    brief = creative_package.get("brief", {})
    prompt = prompt_override or (
        payload.get("detailed_prompt")
        or prompts.get("detailed_generation_prompt")
        or prompts.get("concise_generation_prompt")
        or ""
    )
    negative_prompt = (
        payload.get("negative_prompt")
        or prompts.get("negative_prompt")
        or ""
    )
    request_body = {
        "provider": provider_name,
        "model": model_name,
        "mode": "text-to-video",
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "duration_seconds": int(
            payload.get("duration_seconds")
            or brief.get("duration_seconds")
            or 30
        ),
        "aspect_ratio": payload.get("aspect_ratio") or brief.get("aspect_ratio") or "9:16",
        "resolution": "placeholder-360p",
        "metadata": {
            "product_id": brief.get("product_id", ""),
            "product_name": brief.get("product_name", ""),
            "target_platform": brief.get("target_platform", ""),
            "creative_package_version": creative_package.get("version", ""),
            "prompt_source": "refined" if prompt_override else "original",
            "simulated": provider_name == "Mock Video Provider",
        },
    }
    signature = json.dumps(request_body, sort_keys=True)
    request_id = hashlib.sha256(signature.encode("utf-8")).hexdigest()
    return VideoGenerationRequest(request_id=request_id, **request_body)


def active_job_exists(job):
    return bool(job and getattr(job, "status", None) in ACTIVE_VIDEO_STATUSES)


def submit_video_generation(provider, request, output_dir=None):
    configuration_error = provider.validate_configuration()
    if configuration_error:
        return None, None, configuration_error
    request_error = provider.validate_request(request)
    if request_error:
        return None, None, request_error
    output_dir = output_dir or get_video_output_dir()
    job = provider.submit_generation(request, output_dir)
    return job, None, None


def refresh_video_generation(provider, job):
    if job is None:
        return None, None, VideoGenerationError(
            code="missing_job",
            message="No video generation job is available to refresh.",
            provider="",
            retryable=False,
            user_action="Submit a job first.",
        )
    updated_job = provider.get_job_status(job)
    result = None
    error = None
    if updated_job.status == "completed":
        result = provider.download_result(updated_job)
        if result is None or not is_valid_mp4(result.local_video_path):
            error = VideoGenerationError(
                code="invalid_mp4",
                message="The provider result was missing or was not a valid MP4.",
                provider=updated_job.provider,
                retryable=False,
                user_action="Try a new generation job.",
            )
    elif updated_job.status == "failed":
        error = VideoGenerationError(
            code="mock_failed",
            message=updated_job.message,
            provider=updated_job.provider,
            retryable=False,
            user_action="Submit a new job after changing the request.",
        )
    elif updated_job.status == "timed-out":
        error = VideoGenerationError(
            code="mock_timed_out",
            message=updated_job.message,
            provider=updated_job.provider,
            retryable=True,
            user_action="Refresh again or submit a new job later.",
        )
    return updated_job, result, error


def cancel_video_generation(provider, job):
    if job is None:
        return None
    return provider.cancel_job(job)


def get_video_provider_registry():
    return {
        "Mock Video Provider": MockVideoGenerationProvider(),
    }
