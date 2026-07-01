import tempfile
import unittest
from pathlib import Path

from creative_planning import build_creative_package
from video_generation_provider import (
    MockVideoGenerationProvider,
    VIDEO_STATUS_CANCELLED,
    VIDEO_STATUS_COMPLETED,
    VIDEO_STATUS_FAILED,
    VIDEO_STATUS_PROCESSING,
    VIDEO_STATUS_QUEUED,
    VIDEO_STATUS_SUBMITTED,
    VIDEO_STATUS_TIMED_OUT,
)
from video_generation_service import (
    active_job_exists,
    build_video_generation_request,
    cancel_video_generation,
    is_valid_mp4,
    refresh_video_generation,
    safe_filename,
    submit_video_generation,
)


def product_row():
    return {
        "product_id": "P001",
        "product_name": "AI Resume Builder",
        "category": "Career Software",
        "profit_potential_score": 82.5,
        "product_url": "https://example.com/product",
    }


class VideoGenerationV19Tests(unittest.TestCase):
    def make_package(self):
        return build_creative_package(
            product_row(),
            settings={
                "target_platform": "TikTok",
                "duration_seconds": 20,
                "aspect_ratio": "9:16",
            },
        )

    def test_request_uses_v18_provider_neutral_package(self):
        package = self.make_package()
        request = build_video_generation_request(package)
        self.assertEqual(request.mode, "text-to-video")
        self.assertEqual(request.duration_seconds, 20)
        self.assertEqual(request.aspect_ratio, "9:16")
        self.assertIn("AI Resume Builder", request.prompt)
        self.assertTrue(request.negative_prompt)
        self.assertEqual(request.metadata["creative_package_version"], "1.8")

    def test_request_id_is_deterministic_for_duplicate_prevention(self):
        package = self.make_package()
        first = build_video_generation_request(package)
        second = build_video_generation_request(package)
        self.assertEqual(first.request_id, second.request_id)

    def test_mock_provider_progresses_through_manual_refreshes(self):
        provider = MockVideoGenerationProvider()
        request = build_video_generation_request(self.make_package())
        with tempfile.TemporaryDirectory() as temp_dir:
            job, result, error = submit_video_generation(
                provider,
                request,
                output_dir=Path(temp_dir),
            )
            self.assertEqual(job.status, VIDEO_STATUS_SUBMITTED)
            self.assertIsNone(result)
            self.assertIsNone(error)
            self.assertTrue(active_job_exists(job))

            job, result, error = refresh_video_generation(provider, job)
            self.assertEqual(job.status, VIDEO_STATUS_QUEUED)
            self.assertIsNone(result)
            self.assertIsNone(error)

            job, result, error = refresh_video_generation(provider, job)
            self.assertEqual(job.status, VIDEO_STATUS_PROCESSING)
            self.assertIsNone(result)
            self.assertIsNone(error)

            job, result, error = refresh_video_generation(provider, job)
            self.assertEqual(job.status, VIDEO_STATUS_COMPLETED)
            self.assertIsNone(error)
            self.assertIsNotNone(result)
            self.assertTrue(Path(result.local_video_path).exists())
            self.assertTrue(is_valid_mp4(result.local_video_path))
            self.assertTrue(result.generation_metadata["simulated"])
            self.assertFalse(active_job_exists(job))

    def test_mock_provider_can_cancel_active_job(self):
        provider = MockVideoGenerationProvider()
        request = build_video_generation_request(self.make_package())
        with tempfile.TemporaryDirectory() as temp_dir:
            job, _, _ = submit_video_generation(
                provider,
                request,
                output_dir=Path(temp_dir),
            )
            job = cancel_video_generation(provider, job)
            self.assertEqual(job.status, VIDEO_STATUS_CANCELLED)
            self.assertFalse(active_job_exists(job))

    def test_mock_provider_failed_and_timed_out_states(self):
        request = build_video_generation_request(self.make_package())
        with tempfile.TemporaryDirectory() as temp_dir:
            failed_provider = MockVideoGenerationProvider(forced_outcome="failed")
            failed_job, _, _ = submit_video_generation(
                failed_provider,
                request,
                output_dir=Path(temp_dir),
            )
            failed_job, _, _ = refresh_video_generation(failed_provider, failed_job)
            failed_job, _, failed_error = refresh_video_generation(
                failed_provider,
                failed_job,
            )
            self.assertEqual(failed_job.status, VIDEO_STATUS_FAILED)
            self.assertIsNotNone(failed_error)

            timeout_provider = MockVideoGenerationProvider(forced_outcome="timed-out")
            timeout_job, _, _ = submit_video_generation(
                timeout_provider,
                request,
                output_dir=Path(temp_dir),
            )
            timeout_job, _, _ = refresh_video_generation(timeout_provider, timeout_job)
            timeout_job, _, timeout_error = refresh_video_generation(
                timeout_provider,
                timeout_job,
            )
            self.assertEqual(timeout_job.status, VIDEO_STATUS_TIMED_OUT)
            self.assertTrue(timeout_error.retryable)

    def test_safe_filename_and_invalid_mp4_detection(self):
        self.assertEqual(
            safe_filename("AI Resume Builder / PartnerStack!"),
            "ai-resume-builder-partnerstack",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            bad_path = Path(temp_dir) / "bad.mp4"
            bad_path.write_bytes(b"not a video")
            self.assertFalse(is_valid_mp4(bad_path))


if __name__ == "__main__":
    unittest.main()
