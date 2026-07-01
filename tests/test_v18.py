import io
import json
import unittest
import zipfile
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from creative_planning import (
    ALLOWED_DURATIONS,
    CAMPAIGN_OBJECTIVES,
    CONTENT_TEMPLATES,
    PLATFORM_PRESETS,
    brief_csv_bytes,
    build_creative_package,
    dataframe_csv_bytes,
    json_bytes,
    package_zip_bytes,
    text_bytes,
)
from video_generation_provider import VideoGenerationProvider


PROJECT_DIR = Path(__file__).resolve().parents[1]


def product_row(**overrides):
    row = {
        "product_id": "P001",
        "product_name": "AI Resume Builder",
        "category": "Career Software",
        "profit_potential_score": 82.5,
        "product_url": "https://example.com/product",
    }
    row.update(overrides)
    return row


def offer_row(**overrides):
    row = {
        "offer_id": "O001",
        "product_id": "P001",
        "platform": "PartnerStack",
        "payout_type": "recurring",
        "offer_price": 29,
        "commission_rate": 0.30,
        "commission_value": 8.70,
        "cookie_duration_days": 30,
        "recurring_commission": True,
        "affiliate_url": "https://example.com/offer",
        "offer_status": "active",
        "recommended_offer": True,
    }
    row.update(overrides)
    return row


def video_recommendation(**overrides):
    row = {
        "product_id": "P001",
        "product_name": "AI Resume Builder",
        "category": "Career Software",
        "evidence_level": "product-level evidence",
        "preferred_content_format": "demo",
        "preferred_hook_type": "result_first",
        "suggested_duration_range": "15-29 seconds",
        "feature_to_emphasize": "resume template",
        "evidence_summary": "Product evidence was available.",
    }
    row.update(overrides)
    return row


class CreativePlanningTests(unittest.TestCase):
    def test_product_level_category_and_default_fallback_order(self):
        product_package = build_creative_package(
            product_row(),
            offer=offer_row(),
            video_recommendation=video_recommendation(),
        )
        self.assertEqual(
            product_package["brief"]["source_evidence"],
            "product-level video recommendation",
        )

        category_package = build_creative_package(
            product_row(),
            video_recommendation=video_recommendation(
                evidence_level="category-level fallback"
            ),
        )
        self.assertEqual(
            category_package["brief"]["source_evidence"],
            "category-level video recommendation",
        )

        default_package = build_creative_package(
            product_row(),
            video_recommendation=video_recommendation(
                evidence_level="insufficient evidence",
                preferred_content_format="insufficient observations",
            ),
        )
        self.assertEqual(
            default_package["brief"]["source_evidence"],
            "deterministic default template",
        )
        self.assertIn("deterministic default", " ".join(default_package["brief"]["warnings"]))

    def test_user_overrides_win_and_output_is_deterministic(self):
        settings = {
            "target_platform": "YouTube Shorts",
            "campaign_objective": "product comparison",
            "duration_seconds": 30,
            "aspect_ratio": "1:1",
            "key_product_features": "custom resume scoring, export checklist",
            "template_override": "comparison",
            "hook_type_override": "question",
            "cta": "Compare the details before choosing.",
        }
        first = build_creative_package(
            product_row(),
            offer=offer_row(),
            video_recommendation=video_recommendation(),
            settings=settings,
        )
        second = build_creative_package(
            product_row(),
            offer=offer_row(),
            video_recommendation=video_recommendation(),
            settings=settings,
        )
        self.assertEqual(first["brief"], second["brief"])
        self.assertEqual(first["storyboard"], second["storyboard"])
        self.assertEqual(first["script_text"], second["script_text"])
        self.assertEqual(first["brief"]["selected_template"], "comparison")
        self.assertEqual(first["brief"]["hook_type"], "question")
        self.assertIn("custom resume scoring", first["script_text"])

    def test_scene_timing_no_overlap_and_final_end_matches_duration(self):
        for duration in ALLOWED_DURATIONS:
            package = build_creative_package(
                product_row(),
                settings={"duration_seconds": duration},
            )
            previous_end = 0
            for scene in package["storyboard"]:
                self.assertEqual(scene["start_time"], previous_end)
                self.assertGreater(scene["end_time"], scene["start_time"])
                previous_end = scene["end_time"]
            self.assertEqual(previous_end, duration)

    def test_all_platforms_objectives_and_templates_are_supported(self):
        for platform in PLATFORM_PRESETS:
            for objective in CAMPAIGN_OBJECTIVES:
                package = build_creative_package(
                    product_row(),
                    settings={
                        "target_platform": platform,
                        "campaign_objective": objective,
                    },
                )
                self.assertEqual(package["brief"]["target_platform"], platform)
                self.assertEqual(package["brief"]["campaign_objective"], objective)
                self.assertTrue(package["storyboard"])

        for template in CONTENT_TEMPLATES:
            package = build_creative_package(
                product_row(),
                settings={"template_override": template},
            )
            self.assertEqual(package["brief"]["selected_template"], template)

    def test_offer_status_rules_and_consumer_claim_safeguards(self):
        inactive = build_creative_package(
            product_row(),
            offer=offer_row(offer_status="inactive"),
            settings={"campaign_objective": "offer promotion"},
        )
        self.assertEqual(inactive["brief"]["offer_guidance"], "")
        self.assertIn("Inactive offers", " ".join(inactive["brief"]["warnings"]))

        unknown = build_creative_package(
            product_row(),
            offer=offer_row(offer_status="unknown"),
            settings={"campaign_objective": "offer promotion"},
        )
        self.assertIn("unknown", " ".join(unknown["brief"]["warnings"]).lower())

        active = build_creative_package(
            product_row(),
            offer=offer_row(),
            settings={"campaign_objective": "offer promotion"},
        )
        self.assertNotIn("commission", active["script_text"].lower())
        self.assertNotIn("cookie", active["script_text"].lower())

        unsafe = build_creative_package(
            product_row(),
            settings={"cta": "Guaranteed results with the best product."},
        )
        self.assertIn("Unsupported claim", " ".join(unsafe["validation_warnings"]))

    def test_exports_are_valid_json_csv_text_and_zip(self):
        package = build_creative_package(product_row(), offer=offer_row())
        self.assertEqual(
            json.loads(json_bytes(package["brief"]).decode("utf-8"))["product_id"],
            "P001",
        )
        self.assertIn(b"product_name", brief_csv_bytes(package["brief"]))
        self.assertIn(b"scene_number", dataframe_csv_bytes(package["storyboard"]))
        self.assertIn(b"Video script", text_bytes(package["script_text"]))

        with zipfile.ZipFile(io.BytesIO(package_zip_bytes(package))) as archive:
            names = set(archive.namelist())
        self.assertEqual(
            names,
            {
                "video_brief.json",
                "video_brief.csv",
                "script.txt",
                "storyboard.csv",
                "storyboard.json",
                "generation_prompt.txt",
                "creative_package.json",
            },
        )

    def test_provider_interface_is_abstract_for_real_providers(self):
        with self.assertRaises(NotImplementedError):
            VideoGenerationProvider().get_capabilities()


class CreativeStudioStreamlitTests(unittest.TestCase):
    def make_uploadable_app(self):
        app = AppTest.from_file(str(PROJECT_DIR / "app.py")).run(timeout=30)
        if not hasattr(app.get("file_uploader")[0], "upload"):
            self.skipTest(
                "Streamlit 1.58+ is required for file-upload UI testing"
            )
        return app

    def test_creative_studio_generates_downloads_after_upload(self):
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
        for button in app.get("button"):
            if button.proto.label == "Generate creative package":
                button.click().run(timeout=30)
                break
        else:
            self.fail("Generate creative package button was not found")

        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.tabs), 9)
        labels = {button.proto.label for button in app.get("download_button")}
        for label in {
            "Download video_brief.json",
            "Download video_brief.csv",
            "Download script.txt",
            "Download storyboard.csv",
            "Download storyboard.json",
            "Download generation_prompt.txt",
            "Download creative_package.json",
            "Download complete_creative_package.zip",
        }:
            self.assertIn(label, labels)


if __name__ == "__main__":
    unittest.main()
