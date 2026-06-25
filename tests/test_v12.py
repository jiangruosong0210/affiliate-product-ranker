import unittest
from pathlib import Path

import pandas as pd

from scoring import score_products
from signal_processing import process_signals
from validation import validate_products


PROJECT_DIR = Path(__file__).resolve().parents[1]


def product_row(**overrides):
    row = {
        "product_name": "Test Product",
        "platform": "Test Platform",
        "category": "Test Category",
        "price": 100,
        "commission_rate": 0.20,
        "product_url": "",
        "search_volume": 50_000,
        "search_growth_7d": 0,
        "social_mentions_7d": 5_000,
        "competitor_count": 50,
        "days_until_peak": 30,
        "seasonal_relevance": 50,
    }
    row.update(overrides)
    return row


class SignalProcessingTests(unittest.TestCase):
    def test_negative_search_growth(self):
        scores = process_signals(
            pd.DataFrame(
                [
                    product_row(search_growth_7d=-50),
                    product_row(search_growth_7d=-25),
                    product_row(search_growth_7d=0),
                ]
            )
        )
        self.assertEqual(scores.loc[0, "trend_score"], 0)
        self.assertEqual(scores.loc[1, "trend_score"], 25)
        self.assertEqual(scores.loc[2, "trend_score"], 50)

    def test_values_above_caps_are_clipped(self):
        scores = process_signals(
            pd.DataFrame(
                [
                    product_row(
                        price=200,
                        commission_rate=0.50,
                        search_volume=200_000,
                        search_growth_7d=80,
                        social_mentions_7d=20_000,
                        competitor_count=200,
                    )
                ]
            )
        ).iloc[0]
        self.assertEqual(scores["commission_score"], 100)
        self.assertEqual(scores["search_volume_score"], 100)
        self.assertEqual(scores["social_mentions_score"], 100)
        self.assertEqual(scores["trend_score"], 100)
        self.assertEqual(scores["competition_score"], 100)

    def test_zero_values(self):
        scores = process_signals(
            pd.DataFrame(
                [
                    product_row(
                        price=10,
                        commission_rate=0,
                        search_volume=0,
                        social_mentions_7d=0,
                        competitor_count=0,
                        seasonal_relevance=0,
                    )
                ]
            )
        ).iloc[0]
        self.assertEqual(scores["commission_score"], 0)
        self.assertEqual(scores["demand_score"], 0)
        self.assertEqual(scores["competition_score"], 0)
        self.assertEqual(scores["competition_opportunity"], 100)

    def test_days_until_peak_edges(self):
        scores = process_signals(
            pd.DataFrame(
                [
                    product_row(days_until_peak=0, seasonal_relevance=0),
                    product_row(days_until_peak=30, seasonal_relevance=0),
                    product_row(days_until_peak=60, seasonal_relevance=0),
                    product_row(days_until_peak=90, seasonal_relevance=0),
                ]
            )
        )
        self.assertListEqual(
            scores["timing_urgency_score"].tolist(),
            [100.0, 50.0, 0.0, 0.0],
        )
        self.assertListEqual(
            scores["urgency_score"].tolist(),
            [60.0, 30.0, 0.0, 0.0],
        )

    def test_all_derived_scores_stay_between_zero_and_one_hundred(self):
        products = pd.DataFrame(
            [
                product_row(
                    price=500,
                    commission_rate=1,
                    search_volume=500_000,
                    search_growth_7d=500,
                    social_mentions_7d=100_000,
                    competitor_count=1_000,
                    days_until_peak=0,
                    seasonal_relevance=100,
                ),
                product_row(
                    commission_rate=0,
                    search_volume=0,
                    search_growth_7d=-500,
                    social_mentions_7d=0,
                    competitor_count=0,
                    days_until_peak=1_000,
                    seasonal_relevance=0,
                ),
            ]
        )
        scores = process_signals(products)
        score_columns = [
            "commission_score",
            "search_volume_score",
            "social_mentions_score",
            "trend_score",
            "demand_score",
            "competition_score",
            "competition_opportunity",
            "timing_urgency_score",
            "urgency_score",
        ]
        self.assertTrue(scores[score_columns].ge(0).all().all())
        self.assertTrue(scores[score_columns].le(100).all().all())

    def test_commission_reference_values(self):
        scores = process_signals(
            pd.DataFrame(
                [
                    product_row(price=25, commission_rate=0.20),
                    product_row(price=100, commission_rate=0.20),
                    product_row(price=100, commission_rate=0.50),
                    product_row(price=200, commission_rate=0.50),
                ]
            )
        )
        self.assertLess(scores.loc[0, "commission_score"], scores.loc[1, "commission_score"])
        self.assertEqual(scores.loc[0, "commission_per_sale"], 5)
        self.assertEqual(scores.loc[1, "commission_per_sale"], 20)
        self.assertEqual(scores.loc[2, "commission_score"], 100)
        self.assertEqual(scores.loc[3, "commission_score"], 100)

    def test_commission_score_is_stable_across_uploads(self):
        target = product_row(product_name="Stable Product", price=100, commission_rate=0.20)
        first_score = score_products(pd.DataFrame([target])).iloc[0]["commission_score"]
        second_upload = pd.DataFrame(
            [
                target,
                product_row(product_name="Low Commission", price=10, commission_rate=0.01),
                product_row(product_name="High Commission", price=500, commission_rate=0.50),
            ]
        )
        second_score = score_products(second_upload).loc[
            lambda frame: frame["product_name"] == "Stable Product",
            "commission_score",
        ].iloc[0]
        self.assertEqual(first_score, second_score)


class ValidationAndRankingTests(unittest.TestCase):
    def setUp(self):
        sample = pd.read_csv(PROJECT_DIR / "sample_products.csv")
        self.sample = sample.rename(
            columns={
                "reference_price": "price",
                "reference_commission_rate": "commission_rate",
            }
        )
        self.sample["platform"] = "Test Platform"
        self.sample = self.sample[
            [
                "product_name",
                "platform",
                "category",
                "price",
                "commission_rate",
                "product_url",
                "search_volume",
                "search_growth_7d",
                "social_mentions_7d",
                "competitor_count",
                "days_until_peak",
                "seasonal_relevance",
            ]
        ]

    def test_sample_csv_is_valid(self):
        self.assertEqual(validate_products(self.sample), [])

    def test_invalid_csv_values(self):
        invalid = self.sample.copy()
        invalid["search_growth_7d"] = invalid["search_growth_7d"].astype(object)
        invalid.loc[0, "price"] = 0
        invalid.loc[1, "search_volume"] = -1
        invalid.loc[2, "search_growth_7d"] = "not a number"
        invalid.loc[3, "seasonal_relevance"] = 101
        invalid.loc[4, "product_name"] = ""
        errors = " ".join(validate_products(invalid))
        self.assertIn("price must be greater than 0", errors)
        self.assertIn("search_volume must be greater than or equal to 0", errors)
        self.assertIn("search_growth_7d must contain valid numbers", errors)
        self.assertIn("seasonal_relevance must be between 0 and 100", errors)
        self.assertIn("product_name must contain text", errors)

    def test_ranking_still_works(self):
        ranked = score_products(self.sample)
        self.assertEqual(len(ranked), len(self.sample))
        self.assertTrue(ranked["profit_potential_score"].is_monotonic_decreasing)
        self.assertTrue(ranked["profit_potential_score"].between(0, 100).all())
        self.assertListEqual(ranked["rank"].tolist(), list(range(1, len(ranked) + 1)))
        self.assertIn("commission_per_sale", ranked.columns)
        self.assertIn("commission_score", ranked.columns)


if __name__ == "__main__":
    unittest.main()
