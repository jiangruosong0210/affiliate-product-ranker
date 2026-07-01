import unittest
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from video_insights import add_video_metrics, build_video_recommendations
from video_validation import validate_video_records


PROJECT_DIR = Path(__file__).resolve().parents[1]


def video_row(**overrides):
    row = {
        "video_id": "V-1",
        "product_id": "P-1",
        "platform": "YouTube",
        "title": "Product demo",
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
        "main_feature": "  Ease   Of Use ",
    }
    row.update(overrides)
    return row


def product_frame():
    return pd.DataFrame(
        [
            {
                "product_id": "P-1",
                "product_name": "Product One",
                "category": "Category A",
            },
            {
                "product_id": "P-2",
                "product_name": "Product Two",
                "category": "Category A",
            },
            {
                "product_id": "P-3",
                "product_name": "Product Three",
                "category": "Category A",
            },
            {
                "product_id": "P-4",
                "product_name": "Product Four",
                "category": "Category A",
            },
            {
                "product_id": "P-5",
                "product_name": "Product Five",
                "category": "Category B",
            },
        ]
    )


def prepare_metrics(rows, products=None):
    products = products if products is not None else product_frame()
    valid, excluded, warnings = validate_video_records(
        pd.DataFrame(rows),
        set(products["product_id"]),
    )
    metrics = add_video_metrics(valid).merge(
        products,
        on="product_id",
        how="left",
    )
    return metrics, excluded, warnings


class VideoValidationTests(unittest.TestCase):
    def test_valid_video_is_cleaned(self):
        valid, excluded, warnings = validate_video_records(
            pd.DataFrame([video_row()]),
            {"P-1"},
        )
        self.assertEqual(len(valid), 1)
        self.assertTrue(excluded.empty)
        self.assertTrue(warnings.empty)
        self.assertEqual(valid.iloc[0]["main_feature"], "ease of use")
        self.assertIs(valid.iloc[0]["demo_present"], True)

    def test_duplicate_and_orphan_videos_are_excluded(self):
        rows = [
            video_row(video_id="DUP"),
            video_row(video_id="DUP"),
            video_row(video_id="ORPHAN", product_id="MISSING"),
        ]
        valid, excluded, _ = validate_video_records(
            pd.DataFrame(rows),
            {"P-1"},
        )
        self.assertTrue(valid.empty)
        self.assertEqual(len(excluded), 3)

    def test_negative_and_invalid_controlled_values_are_excluded(self):
        rows = [
            video_row(video_id="NEG", views=-1),
            video_row(video_id="PLATFORM", platform="Unknown"),
            video_row(video_id="FORMAT", content_format="dance"),
            video_row(video_id="HOOK", hook_type="mystery"),
            video_row(video_id="BOOL", cta_present="maybe"),
        ]
        valid, excluded, _ = validate_video_records(
            pd.DataFrame(rows),
            {"P-1"},
        )
        self.assertTrue(valid.empty)
        self.assertEqual(len(excluded), 5)

    def test_missing_optional_metrics_remain_unknown(self):
        valid, excluded, _ = validate_video_records(
            pd.DataFrame(
                [
                    video_row(
                        likes="",
                        comments="",
                        shares="",
                        creator_followers="",
                    )
                ]
            ),
            {"P-1"},
        )
        self.assertTrue(excluded.empty)
        for column in ["likes", "comments", "shares", "creator_followers"]:
            self.assertTrue(pd.isna(valid.iloc[0][column]))
        metrics = add_video_metrics(valid)
        self.assertTrue(pd.isna(metrics.iloc[0]["engagement_rate"]))

    def test_warning_only_rows_remain_valid(self):
        rows = [
            video_row(video_id="URL", video_url="example.com/video"),
            video_row(video_id="LIKES", views=10, likes=11),
        ]
        valid, excluded, warnings = validate_video_records(
            pd.DataFrame(rows),
            {"P-1"},
        )
        self.assertEqual(len(valid), 2)
        self.assertTrue(excluded.empty)
        self.assertEqual(len(warnings), 2)


class VideoMetricTests(unittest.TestCase):
    def test_rates_and_zero_denominators(self):
        metrics, _, _ = prepare_metrics(
            [
                video_row(video_id="NORMAL"),
                video_row(
                    video_id="ZERO-VIEWS",
                    views=0,
                    likes=0,
                    comments=0,
                    shares=0,
                ),
                video_row(
                    video_id="ZERO-FOLLOWERS",
                    creator_followers=0,
                ),
            ]
        )
        normal = metrics.set_index("video_id").loc["NORMAL"]
        self.assertAlmostEqual(normal["engagement_rate"], 0.13)
        self.assertAlmostEqual(normal["like_rate"], 0.10)
        zero_views = metrics.set_index("video_id").loc["ZERO-VIEWS"]
        self.assertTrue(pd.isna(zero_views["engagement_rate"]))
        zero_followers = metrics.set_index("video_id").loc["ZERO-FOLLOWERS"]
        self.assertTrue(pd.isna(zero_followers["view_to_follower_ratio"]))

    def test_partial_engagement_is_not_calculated(self):
        metrics, _, _ = prepare_metrics(
            [video_row(comments="")]
        )
        self.assertTrue(pd.isna(metrics.iloc[0]["engagement_rate"]))
        self.assertAlmostEqual(metrics.iloc[0]["like_rate"], 0.10)
        self.assertAlmostEqual(metrics.iloc[0]["share_rate"], 0.01)


class VideoRecommendationTests(unittest.TestCase):
    def test_product_level_recommendation(self):
        rows = []
        for index in range(5):
            rows.append(
                video_row(
                    video_id=f"P1-{index}",
                    content_format="demo" if index < 3 else "review",
                    hook_type="result_first" if index < 3 else "question",
                    likes=20 if index < 3 else 5,
                    comments=4 if index < 3 else 1,
                    shares=3 if index < 3 else 0,
                    demo_present=index < 3,
                    comparison_present=index >= 3,
                    cta_present=index < 3,
                    duration_seconds=25 if index < 3 else 70,
                )
            )
        metrics, _, _ = prepare_metrics(rows)
        report = build_video_recommendations(metrics, product_frame())
        product = report.set_index("product_id").loc["P-1"]
        self.assertEqual(product["evidence_level"], "product-level evidence")
        self.assertEqual(product["preferred_content_format"], "demo")
        self.assertEqual(product["supporting_video_count"], 5)

    def test_category_fallback(self):
        rows = []
        for product_id in ["P-1", "P-2", "P-3"]:
            for index in range(4):
                rows.append(
                    video_row(
                        video_id=f"{product_id}-{index}",
                        product_id=product_id,
                        content_format="tutorial" if index < 3 else "review",
                        hook_type="problem_solution",
                        likes=15 if index < 3 else 5,
                        comments=3,
                        shares=2,
                    )
                )
        metrics, _, _ = prepare_metrics(rows)
        report = build_video_recommendations(metrics, product_frame())
        product = report.set_index("product_id").loc["P-4"]
        self.assertEqual(product["evidence_level"], "category-level fallback")
        self.assertEqual(product["preferred_content_format"], "tutorial")
        self.assertIn("category evidence", product["evidence_summary"])

    def test_insufficient_evidence(self):
        metrics, _, _ = prepare_metrics([video_row()])
        report = build_video_recommendations(metrics, product_frame())
        product = report.set_index("product_id").loc["P-1"]
        self.assertEqual(product["evidence_level"], "insufficient evidence")


class VideoScaleAndStreamlitTests(unittest.TestCase):
    def make_uploadable_app(self):
        app = AppTest.from_file(str(PROJECT_DIR / "app.py")).run(timeout=30)
        if not hasattr(app.get("file_uploader")[0], "upload"):
            self.skipTest(
                "Streamlit 1.58+ is required for file-upload UI testing"
            )
        return app

    def test_large_video_dataset_has_five_thousand_valid_rows(self):
        videos = pd.read_csv(PROJECT_DIR / "large_sample_videos.csv")
        products = pd.read_csv(PROJECT_DIR / "large_sample_products.csv")
        valid, excluded, warnings = validate_video_records(
            videos,
            set(products["product_id"]),
        )
        metrics = add_video_metrics(valid)
        self.assertEqual(len(videos), 5000)
        self.assertEqual(len(valid), 5000)
        self.assertTrue(excluded.empty)
        self.assertTrue(warnings.empty)
        self.assertEqual(len(metrics), 5000)

    def test_product_only_and_product_offer_workflows(self):
        products = (PROJECT_DIR / "sample_products.csv").read_bytes()
        offers = (PROJECT_DIR / "sample_offers.csv").read_bytes()

        product_only = self.make_uploadable_app()
        product_only.get("file_uploader")[0].upload(
            "products.csv", products, "text/csv"
        ).run(timeout=30)
        self.assertEqual(len(product_only.exception), 0)
        self.assertEqual(len(product_only.tabs), 8)

        with_offers = self.make_uploadable_app()
        with_offers.get("file_uploader")[0].upload(
            "products.csv", products, "text/csv"
        )
        with_offers.get("file_uploader")[1].upload(
            "offers.csv", offers, "text/csv"
        )
        with_offers.run(timeout=30)
        self.assertEqual(len(with_offers.exception), 0)

    def test_complete_video_workflow_and_downloads(self):
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
        self.assertEqual(len(app.tabs), 8)
        labels = {
            button.proto.label for button in app.get("download_button")
        }
        expected = {
            "Download products CSV template",
            "Download offers CSV template",
            "Download video CSV template",
            "Download ranked products",
            "Download offer comparison",
            "Download cleaned videos",
            "Download video exclusions",
            "Download video warnings",
            "Download video recommendations",
            "Download enriched videos",
            "Download video text warnings",
            "Download manual detected comparison",
            "Download extracted feature summary",
        }
        self.assertEqual(labels, expected)
        self.assertTrue(
            all(button.proto.url for button in app.get("download_button"))
        )

    def test_video_quality_downloads_render_for_invalid_fixture(self):
        products = pd.read_csv(PROJECT_DIR / "large_sample_products.csv").head(2)
        app = self.make_uploadable_app()
        app.get("file_uploader")[0].upload(
            "products.csv",
            products.to_csv(index=False).encode("utf-8"),
            "text/csv",
        )
        app.get("file_uploader")[2].upload(
            "videos.csv",
            (PROJECT_DIR / "invalid_sample_videos.csv").read_bytes(),
            "text/csv",
        )
        app.run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        labels = {
            button.proto.label for button in app.get("download_button")
        }
        self.assertIn("Download excluded video records", labels)
        self.assertIn("Download video warning report", labels)
        self.assertTrue(
            all(button.proto.url for button in app.get("download_button"))
        )


if __name__ == "__main__":
    unittest.main()
