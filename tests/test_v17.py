import io
import tempfile
import unittest
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from video_text_analysis import enrich_video_text
from video_upload_processing import (
    MAX_SAMPLED_FRAMES,
    analyze_sampled_frames,
    build_contact_sheet,
    build_sampled_frames_zip,
    build_uploaded_video_text_record,
    extract_video_metadata,
    process_uploaded_video,
    sample_timestamps,
    sample_video_frames,
    save_uploaded_video_temporarily,
    validate_uploaded_video,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]


class FakeUpload(io.BytesIO):
    def __init__(self, content, name="video.mp4", mime_type="video/mp4"):
        super().__init__(content)
        self.name = name
        self.type = mime_type
        self.size = len(content)

    def getvalue(self):
        return super().getvalue()


def synthetic_video_bytes(
    width=96,
    height=160,
    duration=2.0,
    fps=4,
    pattern="changes",
):
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "synthetic.mp4"
        frame_count = max(1, int(duration * fps))
        writer = imageio.get_writer(str(path), fps=fps, codec="libx264")
        for index in range(frame_count):
            if pattern == "black":
                frame = np.zeros((height, width, 3), dtype=np.uint8)
            elif pattern == "duplicate":
                frame = np.full((height, width, 3), 120, dtype=np.uint8)
            else:
                frame = np.zeros((height, width, 3), dtype=np.uint8)
                frame[:, :, 0] = (index * 35) % 255
                frame[:, :, 1] = np.linspace(0, 255, width, dtype=np.uint8)
                frame[:, :, 2] = np.linspace(0, 255, height, dtype=np.uint8)[:, None]
            writer.append_data(frame)
        writer.close()
        return path.read_bytes()


class VideoUploadProcessingTests(unittest.TestCase):
    def test_valid_mp4_metadata_and_visual_outputs(self):
        upload = FakeUpload(synthetic_video_bytes(), "valid.mp4")
        result = process_uploaded_video(
            upload,
            associated_product={
                "product_id": "P001",
                "product_name": "AI Resume Builder",
                "category": "Career Software",
            },
            title="AI Resume Builder demo",
            transcript="Here is a demo. Use code SAVE and export pdf.",
            hashtags="#resume #career",
            language="en",
        )
        self.assertEqual(result["metadata"]["processing_status"], "success")
        self.assertEqual(result["metadata"]["video_orientation"], "vertical")
        self.assertGreater(result["visual_features"]["sampled_frame_count"], 0)
        self.assertTrue(result["contact_sheet_bytes"])
        self.assertTrue(result["sampled_frames_zip_bytes"])
        self.assertEqual(result["association"]["association_status"], "associated")
        enriched, _, _, _ = enrich_video_text(result["text_record"])
        self.assertEqual(enriched.iloc[0]["detected_content_format"], "demo")
        self.assertTrue(enriched.iloc[0]["detected_cta_present"])

    def test_unsupported_oversized_and_corrupted_files_are_rejected_or_failed(self):
        unsupported = FakeUpload(b"not a video", "bad.mov", "video/quicktime")
        valid, errors, _ = validate_uploaded_video(unsupported)
        self.assertFalse(valid)
        self.assertIn("Only MP4", " ".join(errors))

        oversized = FakeUpload(b"x" * (25 * 1024 * 1024 + 1), "big.mp4")
        valid, errors, _ = validate_uploaded_video(oversized)
        self.assertFalse(valid)
        self.assertIn("25 MB", " ".join(errors))

        corrupted = process_uploaded_video(FakeUpload(b"not a video", "bad.mp4"))
        self.assertIn(
            corrupted["metadata"]["processing_status"],
            {"failed", "rejected"},
        )

    def test_duration_limits(self):
        short = process_uploaded_video(
            FakeUpload(synthetic_video_bytes(duration=0.5, fps=4), "short.mp4")
        )
        self.assertEqual(short["metadata"]["processing_status"], "rejected")
        self.assertIn("minimum", short["metadata"]["processing_notes"])

        long = process_uploaded_video(
            FakeUpload(
                synthetic_video_bytes(width=32, height=32, duration=61, fps=1),
                "long.mp4",
            )
        )
        self.assertEqual(long["metadata"]["processing_status"], "rejected")
        self.assertIn("60 second", long["metadata"]["processing_notes"])

    def test_orientation_values(self):
        vertical = process_uploaded_video(
            FakeUpload(synthetic_video_bytes(width=80, height=144), "vertical.mp4")
        )
        horizontal = process_uploaded_video(
            FakeUpload(synthetic_video_bytes(width=144, height=80), "horizontal.mp4")
        )
        square = process_uploaded_video(
            FakeUpload(synthetic_video_bytes(width=96, height=96), "square.mp4")
        )
        self.assertEqual(vertical["metadata"]["video_orientation"], "vertical")
        self.assertEqual(horizontal["metadata"]["video_orientation"], "horizontal")
        self.assertEqual(square["metadata"]["video_orientation"], "square")

    def test_frame_sampling_contact_sheet_and_zip(self):
        timestamps = sample_timestamps(3.0)
        self.assertLessEqual(len(timestamps), MAX_SAMPLED_FRAMES)
        self.assertIn(0.5, timestamps)
        self.assertIn(1.5, timestamps)
        with tempfile.TemporaryDirectory() as temp_dir:
            upload = FakeUpload(synthetic_video_bytes(duration=3), "frames.mp4")
            file_info = save_uploaded_video_temporarily(upload, temp_dir)
            metadata = extract_video_metadata(file_info["path"], file_info)
            frames, notes = sample_video_frames(file_info["path"], metadata, temp_dir)
            self.assertTrue(frames)
            self.assertEqual(notes, "")
            contact_path, contact_bytes = build_contact_sheet(
                frames,
                Path(temp_dir) / "contact.png",
            )
            zip_bytes = build_sampled_frames_zip(frames)
            self.assertTrue(Path(contact_path).exists())
            self.assertTrue(contact_bytes)
            self.assertTrue(zip_bytes)

    def test_black_duplicate_and_scene_change_heuristics(self):
        black = process_uploaded_video(
            FakeUpload(synthetic_video_bytes(pattern="black"), "black.mp4")
        )
        self.assertGreater(black["visual_features"]["black_frame_count"], 0)

        duplicate = process_uploaded_video(
            FakeUpload(synthetic_video_bytes(pattern="duplicate"), "duplicate.mp4")
        )
        self.assertGreaterEqual(
            duplicate["visual_features"]["duplicate_frame_count"],
            1,
        )

        changing = process_uploaded_video(
            FakeUpload(synthetic_video_bytes(pattern="changes"), "change.mp4")
        )
        self.assertGreaterEqual(
            changing["visual_features"]["estimated_scene_change_count"],
            0,
        )

    def test_transcript_record_product_association_and_unassigned(self):
        metadata = {
            "file_hash": "abcdef123456",
            "original_filename": "demo-video.mp4",
        }
        associated = build_uploaded_video_text_record(
            metadata,
            {
                "product_id": "P001",
                "product_name": "AI Resume Builder",
                "category": "Career Software",
            },
            transcript="Step by step tutorial with resume template export pdf.",
        )
        enriched, _, _, _ = enrich_video_text(associated)
        self.assertEqual(enriched.iloc[0]["detected_content_format"], "tutorial")
        self.assertIn("resume template", enriched.iloc[0]["detected_main_features"])

        unassigned = process_uploaded_video(
            FakeUpload(synthetic_video_bytes(), "unassigned.mp4")
        )
        self.assertEqual(unassigned["association"]["association_status"], "unassigned")
        self.assertIn("No product association", " ".join(unassigned["warnings"]))

    def test_duplicate_file_warning_input_has_stable_hash(self):
        content = synthetic_video_bytes()
        first = process_uploaded_video(FakeUpload(content, "a.mp4"))
        second = process_uploaded_video(FakeUpload(content, "b.mp4"))
        self.assertEqual(first["metadata"]["file_hash"], second["metadata"]["file_hash"])


class VideoUploadStreamlitTests(unittest.TestCase):
    def make_uploadable_app(self):
        app = AppTest.from_file(str(PROJECT_DIR / "app.py")).run(timeout=30)
        if not hasattr(app.get("file_uploader")[0], "upload"):
            self.skipTest(
                "Streamlit 1.58+ is required for file-upload UI testing"
            )
        return app

    def test_streamlit_video_upload_section_and_downloads(self):
        app = self.make_uploadable_app()
        app.get("file_uploader")[0].upload(
            "products.csv",
            (PROJECT_DIR / "sample_products.csv").read_bytes(),
            "text/csv",
        )
        app.get("file_uploader")[3].upload(
            "uploaded.mp4",
            synthetic_video_bytes(),
            "video/mp4",
        )
        app.get("text_area")[1].input(
            "Here is a demo. Use code SAVE and export pdf."
        )
        app.get("button")[-1].click().run(timeout=60)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.tabs), 7)
        labels = {button.proto.label for button in app.get("download_button")}
        for label in {
            "Download video metadata",
            "Download sampled frames ZIP",
            "Download contact sheet",
            "Download video processing report",
            "Download uploaded video text analysis",
        }:
            self.assertIn(label, labels)


if __name__ == "__main__":
    unittest.main()
