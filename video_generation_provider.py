from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import imageio.v2 as imageio
import numpy as np


VIDEO_STATUS_SUBMITTED = "submitted"
VIDEO_STATUS_QUEUED = "queued"
VIDEO_STATUS_PROCESSING = "processing"
VIDEO_STATUS_COMPLETED = "completed"
VIDEO_STATUS_FAILED = "failed"
VIDEO_STATUS_TIMED_OUT = "timed-out"
VIDEO_STATUS_CANCELLED = "cancelled"

ACTIVE_VIDEO_STATUSES = {
    VIDEO_STATUS_SUBMITTED,
    VIDEO_STATUS_QUEUED,
    VIDEO_STATUS_PROCESSING,
}
TERMINAL_VIDEO_STATUSES = {
    VIDEO_STATUS_COMPLETED,
    VIDEO_STATUS_FAILED,
    VIDEO_STATUS_TIMED_OUT,
    VIDEO_STATUS_CANCELLED,
}


@dataclass(frozen=True)
class VideoProviderCapabilities:
    provider_name: str
    supported_modes: list[str]
    supported_durations: list[int]
    supported_aspect_ratios: list[str]
    supported_resolutions: list[str]
    supports_negative_prompt: bool
    supports_seed: bool
    supports_image_input: bool
    supports_cancel: bool
    supports_credit_balance: bool
    max_prompt_chars: int | None
    cost_label: str
    notes: str


@dataclass(frozen=True)
class VideoGenerationRequest:
    request_id: str
    provider: str
    model: str
    mode: str
    prompt: str
    negative_prompt: str
    duration_seconds: int
    aspect_ratio: str
    resolution: str
    seed: int | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class VideoGenerationJob:
    job_id: str
    request_id: str
    provider: str
    model: str
    status: str
    submitted_at: str
    updated_at: str
    progress: float | None = None
    message: str = ""
    provider_metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class VideoGenerationResult:
    job_id: str
    local_video_path: str
    remote_video_url: str
    mime_type: str
    file_size_bytes: int
    duration_seconds: float | None
    provider: str
    model: str
    generation_metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class VideoGenerationError:
    code: str
    message: str
    provider: str
    retryable: bool
    user_action: str
    provider_metadata: dict = field(default_factory=dict)


class VideoGenerationProvider:
    def get_capabilities(self):
        raise NotImplementedError

    def validate_configuration(self):
        raise NotImplementedError

    def validate_request(self, request):
        raise NotImplementedError

    def submit_generation(self, request, output_dir):
        raise NotImplementedError

    def get_job_status(self, job):
        raise NotImplementedError

    def download_result(self, job):
        raise NotImplementedError

    def cancel_job(self, job):
        raise NotImplementedError


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dataclass_to_dict(value):
    return asdict(value)


class MockVideoGenerationProvider(VideoGenerationProvider):
    provider_name = "Mock Video Provider"
    model_name = "mock-placeholder-video-v1"

    def __init__(self, forced_outcome="completed"):
        self.forced_outcome = forced_outcome

    def get_capabilities(self):
        return VideoProviderCapabilities(
            provider_name=self.provider_name,
            supported_modes=["text-to-video"],
            supported_durations=[15, 20, 30, 45, 60],
            supported_aspect_ratios=["9:16", "1:1", "16:9", "4:5"],
            supported_resolutions=["placeholder-360p"],
            supports_negative_prompt=True,
            supports_seed=True,
            supports_image_input=False,
            supports_cancel=True,
            supports_credit_balance=False,
            max_prompt_chars=4000,
            cost_label="simulated free mock output",
            notes=(
                "Creates a local placeholder MP4 for workflow testing. "
                "It is not AI-generated market or creative output."
            ),
        )

    def validate_configuration(self):
        return None

    def validate_request(self, request):
        capabilities = self.get_capabilities()
        if request.mode not in capabilities.supported_modes:
            return VideoGenerationError(
                code="unsupported_mode",
                message="The mock provider only supports text-to-video.",
                provider=self.provider_name,
                retryable=False,
                user_action="Use text-to-video mode.",
            )
        if request.duration_seconds not in capabilities.supported_durations:
            return VideoGenerationError(
                code="unsupported_duration",
                message="The selected duration is not supported by the mock provider.",
                provider=self.provider_name,
                retryable=False,
                user_action="Choose one of the supported V1.8 durations.",
            )
        if request.aspect_ratio not in capabilities.supported_aspect_ratios:
            return VideoGenerationError(
                code="unsupported_aspect_ratio",
                message="The selected aspect ratio is not supported by the mock provider.",
                provider=self.provider_name,
                retryable=False,
                user_action="Choose 9:16, 1:1, 16:9, or 4:5.",
            )
        if not request.prompt.strip():
            return VideoGenerationError(
                code="missing_prompt",
                message="A prompt is required before creating a video job.",
                provider=self.provider_name,
                retryable=False,
                user_action="Generate a V1.8 creative package first.",
            )
        if capabilities.max_prompt_chars and len(request.prompt) > capabilities.max_prompt_chars:
            return VideoGenerationError(
                code="prompt_too_long",
                message="The prompt is too long for this provider.",
                provider=self.provider_name,
                retryable=False,
                user_action="Shorten the prompt before submitting.",
            )
        return None

    def submit_generation(self, request, output_dir):
        now = utc_now()
        job_id = f"mock-{request.request_id[:16]}"
        return VideoGenerationJob(
            job_id=job_id,
            request_id=request.request_id,
            provider=self.provider_name,
            model=self.model_name,
            status=VIDEO_STATUS_SUBMITTED,
            submitted_at=now,
            updated_at=now,
            progress=0.05,
            message="Mock video job submitted. This is simulated workflow data.",
            provider_metadata={
                "refresh_count": 0,
                "forced_outcome": self.forced_outcome,
                "output_dir": str(output_dir),
                "simulated": True,
            },
        )

    def get_job_status(self, job):
        if job.status in TERMINAL_VIDEO_STATUSES:
            return job
        refresh_count = int(job.provider_metadata.get("refresh_count", 0)) + 1
        outcome = job.provider_metadata.get("forced_outcome", self.forced_outcome)
        if outcome == VIDEO_STATUS_FAILED and refresh_count >= 2:
            return self._updated_job(
                job,
                VIDEO_STATUS_FAILED,
                1.0,
                "Mock job failed intentionally for workflow testing.",
                refresh_count,
            )
        if outcome == VIDEO_STATUS_TIMED_OUT and refresh_count >= 2:
            return self._updated_job(
                job,
                VIDEO_STATUS_TIMED_OUT,
                1.0,
                "Mock job timed out intentionally for workflow testing.",
                refresh_count,
            )

        if refresh_count == 1:
            return self._updated_job(
                job,
                VIDEO_STATUS_QUEUED,
                0.25,
                "Mock job is queued.",
                refresh_count,
            )
        if refresh_count == 2:
            return self._updated_job(
                job,
                VIDEO_STATUS_PROCESSING,
                0.65,
                "Mock job is processing.",
                refresh_count,
            )

        output_path = self._create_placeholder_video(job)
        updated = self._updated_job(
            job,
            VIDEO_STATUS_COMPLETED,
            1.0,
            "Mock placeholder MP4 completed. This was not generated by an AI video model.",
            refresh_count,
        )
        updated.provider_metadata["local_video_path"] = str(output_path)
        updated.provider_metadata["file_size_bytes"] = output_path.stat().st_size
        return updated

    def download_result(self, job):
        path = Path(job.provider_metadata.get("local_video_path", ""))
        if job.status != VIDEO_STATUS_COMPLETED or not path.exists():
            return None
        return VideoGenerationResult(
            job_id=job.job_id,
            local_video_path=str(path),
            remote_video_url="",
            mime_type="video/mp4",
            file_size_bytes=path.stat().st_size,
            duration_seconds=2.0,
            provider=job.provider,
            model=job.model,
            generation_metadata={
                "simulated": True,
                "label": "Mock placeholder MP4. Not AI-generated.",
            },
        )

    def cancel_job(self, job):
        if job.status in TERMINAL_VIDEO_STATUSES:
            return job
        return self._updated_job(
            job,
            VIDEO_STATUS_CANCELLED,
            job.progress,
            "Mock video job cancelled.",
            int(job.provider_metadata.get("refresh_count", 0)),
        )

    def _updated_job(self, job, status, progress, message, refresh_count):
        metadata = dict(job.provider_metadata)
        metadata["refresh_count"] = refresh_count
        return VideoGenerationJob(
            job_id=job.job_id,
            request_id=job.request_id,
            provider=job.provider,
            model=job.model,
            status=status,
            submitted_at=job.submitted_at,
            updated_at=utc_now(),
            progress=progress,
            message=message,
            provider_metadata=metadata,
        )

    def _create_placeholder_video(self, job):
        output_dir = Path(job.provider_metadata["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{job.job_id}.mp4"
        if path.exists():
            return path

        writer = imageio.get_writer(
            str(path),
            format="FFMPEG",
            fps=6,
            codec="libx264",
            macro_block_size=16,
        )
        try:
            base = sum(ord(char) for char in job.request_id) % 120
            for index in range(12):
                frame = np.zeros((368, 240, 3), dtype=np.uint8)
                frame[:, :, 0] = (base + index * 8) % 255
                frame[:, :, 1] = (70 + index * 11) % 255
                frame[:, :, 2] = 150
                band_start = 20 + index * 4
                frame[band_start : band_start + 36, 24:216, :] = 245
                writer.append_data(frame)
        finally:
            writer.close()
        return path
