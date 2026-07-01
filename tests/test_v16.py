import unittest
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from schemas import VIDEO_COLUMNS
from video_text_analysis import apply_label_precedence, enrich_video_text
from video_validation import validate_video_records


PROJECT_DIR = Path(__file__).resolve().parents[1]


def video_row(**overrides):
    row = {
        "video_id": "V-1",
        "product_id": "P001",
        "platform": "YouTube",
        "title": "AI Resume Builder demo",
        "video_url": "https://example.com/video",
        "publish_date": "2026-01-01",
        "duration_seconds": 30,
        "views": 100,
        "likes": 10,
        "comments": 2,
        "shares": 1,
        "creator_followers": 1000,
        "content_format": "demo",
        "hook_type": "result_first",
        "demo_present": True,
        "comparison_present": False,
        "cta_present": True,
        "main_feature": "resume template",
        "description": "",
        "transcript": "",
        "hashtags": "",
        "creator_name": "",
        "language": "",
        "category": "Career Software",
        "product_name": "AI Resume Builder",
    }
    row.update(overrides)
    return row


class VideoTextAnalysisTests(unittest.TestCase):
    def enrich_one(self, **overrides):
        enriched, warnings, comparison, features = enrich_video_text(
            pd.DataFrame([video_row(**overrides)])
        )
        return enriched.iloc[0], warnings, comparison.iloc[0], features

    def test_version_15_video_without_text_fields_still_validates(self):
        row = {column: video_row()[column] for column in VIDEO_COLUMNS}
        valid, excluded, warnings = validate_video_records(
            pd.DataFrame([row]),
            {"P001"},
        )
        self.assertEqual(len(valid), 1)
        self.assertTrue(excluded.empty)
        self.assertTrue(warnings.empty)
        for column in ["description", "transcript", "hashtags", "creator_name", "language"]:
            self.assertIn(column, valid.columns)

    def test_blank_optional_text_is_not_excluded(self):
        enriched, warnings, _, _ = self.enrich_one(
            title="",
            description="",
            transcript="",
            hashtags="",
            language="",
        )
        self.assertEqual(enriched["text_analysis_status"], "no_text")
        self.assertEqual(enriched["normalized_language"], "unknown")
        self.assertTrue(warnings.empty)

    def test_title_only_analysis_detects_format_hook_and_cta(self):
        enriched, _, _, _ = self.enrich_one(
            title="Top 5 AI resume tools? Use code SAVE today",
            content_format="other",
            hook_type="other",
            cta_present="",
        )
        self.assertEqual(enriched["detected_content_format"], "listicle")
        self.assertEqual(enriched["detected_hook_type"], "discount_offer")
        self.assertTrue(enriched["detected_cta_present"])
        self.assertEqual(enriched["detected_cta_type"], "discount_code")

    def test_transcript_only_analysis(self):
        enriched, _, _, _ = self.enrich_one(
            title="",
            transcript=(
                "Struggling with resumes? Here is how to fix your resume "
                "template and export pdf workflow step by step."
            ),
        )
        self.assertEqual(enriched["detected_content_format"], "tutorial")
        self.assertEqual(enriched["detected_hook_type"], "problem_solution")
        self.assertIn("resume template", enriched["detected_main_features"])
        self.assertIn("export pdf", enriched["detected_main_features"])

    def test_description_and_hashtag_analysis(self):
        enriched, _, _, _ = self.enrich_one(
            title="",
            description="Honest review with pros and cons.",
            hashtags="#Resume #CareerTools",
        )
        self.assertEqual(enriched["detected_content_format"], "review")
        self.assertEqual(enriched["hashtag_list"], "resume; careertools")

    def test_ambiguous_format_uses_priority_and_preserves_evidence(self):
        enriched, _, _, _ = self.enrich_one(
            title="AI Resume Builder review vs old templates",
            description="This demo shows how it works.",
        )
        self.assertEqual(enriched["detected_content_format"], "comparison")
        self.assertIn("review", enriched["detected_content_format_all_evidence"])
        self.assertIn("demo", enriched["detected_content_format_all_evidence"])
        self.assertIn("ambiguous", enriched["detected_content_format_notes"])

    def test_cta_negation_and_multiple_cta_types(self):
        negated, _, _, _ = self.enrich_one(
            title="Do not buy now, no link in bio for this review",
        )
        self.assertFalse(negated["detected_cta_present"])
        self.assertIn("negated", negated["detected_cta_notes"])

        multiple, _, _, _ = self.enrich_one(
            title="Use my code and check the link in description",
        )
        self.assertTrue(multiple["detected_cta_present"])
        self.assertEqual(multiple["detected_cta_type"], "discount_code")
        self.assertIn("multiple", multiple["detected_cta_notes"])

    def test_generic_words_do_not_become_features(self):
        enriched, _, _, _ = self.enrich_one(
            title="Best amazing product video buy now",
            description="Good great super product review",
            category="Unknown Category",
        )
        self.assertEqual(enriched["detected_feature_count"], 0)

    def test_feature_output_is_deterministic(self):
        first, _, _, _ = self.enrich_one(
            transcript="resume template resume template export pdf ai suggestions",
        )
        second, _, _, _ = self.enrich_one(
            transcript="resume template resume template export pdf ai suggestions",
        )
        self.assertEqual(
            first["detected_main_features"],
            second["detected_main_features"],
        )

    def test_comparison_statuses(self):
        exact, _, exact_comparison, _ = self.enrich_one(
            title="Demo of resume template",
            content_format="demo",
            main_feature="resume template",
        )
        self.assertEqual(exact_comparison["content_format_agreement"], "exact_match")
        self.assertEqual(exact_comparison["main_feature_agreement"], "exact_match")

        _, _, mismatch, _ = self.enrich_one(
            title="Honest review with pros and cons",
            content_format="demo",
        )
        self.assertEqual(mismatch["content_format_agreement"], "mismatch")

        _, _, partial, _ = self.enrich_one(
            transcript="resume template export pdf ai suggestions",
            main_feature="template",
        )
        self.assertEqual(partial["main_feature_agreement"], "partial_match")

    def test_label_precedence_modes(self):
        enriched, _, _, _ = enrich_video_text(
            pd.DataFrame(
                [
                    video_row(
                        title="Honest review with pros and cons",
                        content_format="demo",
                        hook_type="",
                        cta_present=pd.NA,
                        main_feature="",
                    )
                ]
            )
        )
        manual_first = apply_label_precedence(
            enriched,
            "Manual first, detected fallback",
        ).iloc[0]
        self.assertEqual(manual_first["effective_content_format"], "demo")
        self.assertEqual(manual_first["effective_hook_type"], "other")

        detected_only = apply_label_precedence(enriched, "Detected labels only").iloc[0]
        self.assertEqual(detected_only["effective_content_format"], "review")

        compare_only = apply_label_precedence(enriched, "Compare only").iloc[0]
        self.assertEqual(compare_only["content_format"], "demo")
        self.assertEqual(compare_only["label_source"], "compare_only")

    def test_unknown_unsupported_language_long_and_duplicate_text_warnings(self):
        long_text = "resume template " * 700
        rows = pd.DataFrame(
            [
                video_row(video_id="V1", title="same text", language=""),
                video_row(video_id="V2", title="same text", language="es"),
                video_row(video_id="V3", transcript=long_text, language="en"),
            ]
        )
        enriched, warnings, _, _ = enrich_video_text(rows)
        self.assertEqual(
            enriched.set_index("video_id").loc["V1", "normalized_language"],
            "unknown",
        )
        self.assertEqual(
            enriched.set_index("video_id").loc["V2", "text_analysis_status"],
            "unsupported_language",
        )
        self.assertEqual(
            enriched.set_index("video_id").loc["V3", "text_analysis_status"],
            "too_long_truncated",
        )
        warning_text = " ".join(warnings["warning_reasons"])
        self.assertIn("duplicate text", warning_text)
        self.assertIn("unsupported language", warning_text)
        self.assertIn("analysis text truncated", warning_text)


class VideoTextStreamlitTests(unittest.TestCase):
    def make_uploadable_app(self):
        app = AppTest.from_file(str(PROJECT_DIR / "app.py")).run(timeout=30)
        if not hasattr(app.get("file_uploader")[0], "upload"):
            self.skipTest(
                "Streamlit 1.58+ is required for file-upload UI testing"
            )
        return app

    def test_full_workflow_has_eight_tabs_and_v16_downloads(self):
        app = self.make_uploadable_app()
        app.get("file_uploader")[0].upload(
            "products.csv",
            (PROJECT_DIR / "sample_products.csv").read_bytes(),
            "text/csv",
        )
        app.get("file_uploader")[1].upload(
            "offers.csv",
            (PROJECT_DIR / "sample_offers.csv").read_bytes(),
            "text/csv",
        )
        app.get("file_uploader")[2].upload(
            "videos.csv",
            (PROJECT_DIR / "sample_videos.csv").read_bytes(),
            "text/csv",
        )
        app.run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.tabs), 9)
        labels = {button.proto.label for button in app.get("download_button")}
        for label in {
            "Download enriched videos",
            "Download video text warnings",
            "Download manual detected comparison",
            "Download extracted feature summary",
        }:
            self.assertIn(label, labels)

    def test_large_text_enriched_dataset(self):
        videos = pd.read_csv(PROJECT_DIR / "large_sample_videos.csv")
        products = pd.read_csv(PROJECT_DIR / "large_sample_products.csv")
        valid, excluded, _ = validate_video_records(
            videos,
            set(products["product_id"]),
        )
        merged = valid.merge(
            products[["product_id", "product_name", "category"]],
            on="product_id",
            how="left",
        )
        enriched, warnings, comparison, features = enrich_video_text(merged)
        self.assertEqual(len(videos), 5000)
        self.assertEqual(len(valid), 5000)
        self.assertTrue(excluded.empty)
        self.assertEqual(len(enriched), 5000)
        self.assertEqual(len(comparison), 5000)
        self.assertFalse(features.empty)
        self.assertLess(len(warnings), 5000)


if __name__ == "__main__":
    unittest.main()
