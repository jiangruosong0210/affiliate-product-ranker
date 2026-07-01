import unittest
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from data_quality import validate_offer_records, validate_product_records
from generate_test_data import generate_clean_data
from market_data.manual_provider import ManualProvider
from market_data.service import process_market_data
from offer_scoring import OFFER_SCORING_CONFIG, score_offers
from scoring import score_products


PROJECT_DIR = Path(__file__).resolve().parents[1]


def offer_row(**overrides):
    row = {
        "offer_id": "O-1",
        "product_id": "P-1",
        "platform": "Platform A",
        "payout_type": "one_time",
        "offer_price": 100,
        "commission_rate": 0.20,
        "fixed_commission_amount": "",
        "commission_per_lead": "",
        "cookie_duration_days": 30,
        "recurring_commission": False,
        "affiliate_url": "",
        "offer_status": "active",
    }
    row.update(overrides)
    return row


class OfferValidationTests(unittest.TestCase):
    def test_one_product_can_have_multiple_valid_offers(self):
        offers = pd.DataFrame(
            [
                offer_row(offer_id="O-1", platform="Platform A"),
                offer_row(
                    offer_id="O-2",
                    platform="Platform B",
                    offer_price=120,
                    commission_rate=0.30,
                ),
            ]
        )
        valid, excluded = validate_offer_records(offers, {"P-1"})
        self.assertEqual(len(valid), 2)
        self.assertTrue(excluded.empty)

    def test_payout_specific_commission_values(self):
        offers = pd.DataFrame(
            [
                offer_row(offer_id="O-1", payout_type="one_time"),
                offer_row(
                    offer_id="O-2",
                    payout_type="recurring",
                    recurring_commission=True,
                    offer_price=50,
                    commission_rate=0.40,
                ),
                offer_row(
                    offer_id="O-3",
                    payout_type="fixed_amount",
                    offer_price="",
                    commission_rate="",
                    fixed_commission_amount=35,
                ),
                offer_row(
                    offer_id="O-4",
                    payout_type="lead",
                    offer_price="",
                    commission_rate="",
                    commission_per_lead=12,
                ),
            ]
        )
        valid, excluded = validate_offer_records(offers, {"P-1"})
        self.assertTrue(excluded.empty)
        scored = score_offers(valid).set_index("offer_id")
        self.assertEqual(scored.loc["O-1", "commission_value"], 20)
        self.assertEqual(scored.loc["O-2", "commission_value"], 20)
        self.assertEqual(scored.loc["O-3", "commission_value"], 35)
        self.assertEqual(scored.loc["O-4", "commission_value"], 12)

    def test_percentage_rate_must_be_greater_than_zero(self):
        valid, excluded = validate_offer_records(
            pd.DataFrame([offer_row(commission_rate=0)]),
            {"P-1"},
        )
        self.assertTrue(valid.empty)
        self.assertIn("0 < commission_rate <= 1", excluded.iloc[0]["exclusion_reasons"])

    def test_recurring_flag_must_match_payout_type(self):
        offers = pd.DataFrame(
            [
                offer_row(
                    offer_id="O-1",
                    payout_type="recurring",
                    recurring_commission=False,
                ),
                offer_row(
                    offer_id="O-2",
                    payout_type="one_time",
                    recurring_commission=True,
                ),
            ]
        )
        valid, excluded = validate_offer_records(offers, {"P-1"})
        self.assertTrue(valid.empty)
        self.assertEqual(len(excluded), 2)

    def test_fixed_and_lead_weights_sum_to_one(self):
        weights = OFFER_SCORING_CONFIG["fixed_lead_weights"]
        self.assertAlmostEqual(sum(weights.values()), 1.0)

    def test_fixed_and_lead_have_no_rate_or_recurring_contribution(self):
        offers = pd.DataFrame(
            [
                offer_row(
                    payout_type="fixed_amount",
                    offer_price="",
                    commission_rate="",
                    fixed_commission_amount=50,
                )
            ]
        )
        valid, _ = validate_offer_records(offers, {"P-1"})
        scored = score_offers(valid).iloc[0]
        self.assertEqual(scored["commission_rate_contribution"], 0)
        self.assertEqual(scored["recurring_contribution"], 0)

    def test_orphan_and_duplicate_offers_are_excluded(self):
        offers = pd.DataFrame(
            [
                offer_row(offer_id="DUP", product_id="P-1"),
                offer_row(offer_id="DUP", product_id="MISSING"),
            ]
        )
        valid, excluded = validate_offer_records(offers, {"P-1"})
        self.assertTrue(valid.empty)
        self.assertEqual(len(excluded), 2)
        self.assertIn("duplicate offer_id", excluded.iloc[0]["exclusion_reasons"])
        self.assertIn("orphan offer", excluded.iloc[1]["exclusion_reasons"])


class OfferScoringTests(unittest.TestCase):
    def test_offer_scores_stay_between_zero_and_one_hundred(self):
        offers = pd.DataFrame(
            [
                offer_row(offer_id="LOW", offer_price=5, commission_rate=0.01),
                offer_row(
                    offer_id="HIGH",
                    offer_price=10_000,
                    commission_rate=1,
                    cookie_duration_days=365,
                ),
            ]
        )
        valid, _ = validate_offer_records(offers, {"P-1"})
        scored = score_offers(valid)
        self.assertTrue(scored["platform_offer_score"].between(0, 100).all())

    def test_price_rate_and_cookie_duration_affect_score(self):
        offers = pd.DataFrame(
            [
                offer_row(
                    offer_id="LOW",
                    offer_price=50,
                    commission_rate=0.10,
                    cookie_duration_days=1,
                ),
                offer_row(
                    offer_id="HIGH",
                    offer_price=150,
                    commission_rate=0.30,
                    cookie_duration_days=90,
                ),
            ]
        )
        valid, _ = validate_offer_records(offers, {"P-1"})
        scored = score_offers(valid).set_index("offer_id")
        self.assertGreater(
            scored.loc["HIGH", "platform_offer_score"],
            scored.loc["LOW", "platform_offer_score"],
        )

    def test_recommendation_prefers_active_and_never_inactive(self):
        offers = pd.DataFrame(
            [
                offer_row(offer_id="ACTIVE", offer_status="active"),
                offer_row(
                    offer_id="INACTIVE",
                    offer_status="inactive",
                    offer_price=1000,
                    commission_rate=1,
                ),
            ]
        )
        valid, _ = validate_offer_records(offers, {"P-1"})
        scored = score_offers(valid).set_index("offer_id")
        self.assertTrue(scored.loc["ACTIVE", "recommended_offer"])
        self.assertFalse(scored.loc["INACTIVE", "recommended_offer"])

    def test_unknown_is_used_only_without_active_offer(self):
        offers = pd.DataFrame(
            [
                offer_row(offer_id="UNKNOWN", offer_status="unknown"),
                offer_row(offer_id="INACTIVE", offer_status="inactive"),
            ]
        )
        valid, _ = validate_offer_records(offers, {"P-1"})
        scored = score_offers(valid).set_index("offer_id")
        self.assertTrue(scored.loc["UNKNOWN", "recommended_offer"])
        self.assertTrue(scored.loc["UNKNOWN", "recommendation_warning"])


class DatasetAndRegressionTests(unittest.TestCase):
    def test_clean_generator_counts_and_validity(self):
        products, offers = generate_clean_data()
        self.assertEqual(len(products), 1000)
        self.assertEqual(len(offers), 2500)
        valid_products, excluded_products = validate_product_records(
            pd.DataFrame(products),
            mode="manual",
        )
        valid_offers, excluded_offers = validate_offer_records(
            pd.DataFrame(offers),
            set(valid_products["product_id"]),
        )
        self.assertEqual(len(valid_products), 1000)
        self.assertEqual(len(valid_offers), 2500)
        self.assertTrue(excluded_products.empty)
        self.assertTrue(excluded_offers.empty)

    def test_generated_data_is_deterministic(self):
        first_products, first_offers = generate_clean_data()
        second_products, second_offers = generate_clean_data()
        self.assertEqual(first_products, second_products)
        self.assertEqual(first_offers, second_offers)

    def test_large_file_processing_completes(self):
        products = pd.read_csv(PROJECT_DIR / "large_sample_products.csv")
        offers = pd.read_csv(PROJECT_DIR / "large_sample_offers.csv")
        valid_products, excluded_products = validate_product_records(
            products,
            mode="manual",
        )
        signal_df, failures = process_market_data(
            valid_products,
            ManualProvider(),
            result_cache={},
        )
        ranked = score_products(signal_df)
        valid_offers, excluded_offers = validate_offer_records(
            offers,
            set(valid_products["product_id"]),
        )
        scored_offers = score_offers(valid_offers)
        self.assertEqual(len(ranked), 1000)
        self.assertEqual(len(scored_offers), 2500)
        self.assertTrue(excluded_products.empty)
        self.assertTrue(excluded_offers.empty)
        self.assertTrue(failures.empty)

    def test_saved_scalability_files_have_exact_clean_counts(self):
        products = pd.read_csv(PROJECT_DIR / "large_sample_products.csv")
        offers = pd.read_csv(PROJECT_DIR / "large_sample_offers.csv")
        valid_products, excluded_products = validate_product_records(
            products,
            mode="manual",
        )
        valid_offers, excluded_offers = validate_offer_records(
            offers,
            set(valid_products["product_id"]),
        )
        self.assertEqual(len(products), 1000)
        self.assertEqual(len(offers), 2500)
        self.assertEqual(len(valid_products), 1000)
        self.assertEqual(len(valid_offers), 2500)
        self.assertTrue(excluded_products.empty)
        self.assertTrue(excluded_offers.empty)

    def test_invalid_fixtures_are_separate_and_excluded(self):
        invalid_products = pd.read_csv(PROJECT_DIR / "invalid_sample_products.csv")
        invalid_offers = pd.read_csv(PROJECT_DIR / "invalid_sample_offers.csv")
        _, excluded_products = validate_product_records(
            invalid_products,
            mode="manual",
        )
        _, excluded_offers = validate_offer_records(
            invalid_offers,
            {"P0001", "P0002"},
        )
        self.assertEqual(len(excluded_products), len(invalid_products))
        self.assertEqual(len(excluded_offers), len(invalid_offers))

    def test_streamlit_app_imports_cleanly(self):
        app = AppTest.from_file(str(PROJECT_DIR / "app.py")).run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.tabs), 8)
        self.assertEqual(len(app.get("file_uploader")), 5)


if __name__ == "__main__":
    unittest.main()
