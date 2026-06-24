import unittest
from pathlib import Path

import pandas as pd

from keyword_generation import generate_keywords
from market_data.base_provider import (
    IncompleteResponseError,
    MarketDataProvider,
    MarketDataResult,
    ProviderTimeoutError,
    utc_now_iso,
    validate_provider_result,
)
from market_data.manual_provider import ManualProvider
from market_data.mock_provider import MockProvider
from market_data.service import process_market_data
from scoring import score_products
from validation import SIGNAL_COLUMNS, validate_products


PROJECT_DIR = Path(__file__).resolve().parents[1]


def core_product(**overrides):
    product = {
        "product_name": "AI Resume Builder",
        "platform": "PartnerStack",
        "category": "Career Software",
        "price": 29,
        "commission_rate": 0.30,
        "product_url": "https://example.com/ai-resume-builder",
    }
    product.update(overrides)
    return product


def market_result(**overrides):
    values = {
        "search_volume": 50_000,
        "search_growth_7d": 10,
        "social_mentions_7d": 5_000,
        "competitor_count": 40,
        "days_until_peak": 20,
        "seasonal_relevance": 70,
        "data_source": "test provider",
        "retrieved_at": utc_now_iso(),
        "confidence_level": "medium",
        "retrieval_status": "success",
        "error_message": "",
    }
    values.update(overrides)
    return MarketDataResult(**values)


class SuccessfulProvider(MarketDataProvider):
    provider_name = "successful provider"

    def retrieve(self, product, keywords):
        return market_result()


class FailingProvider(MarketDataProvider):
    provider_name = "failing provider"

    def retrieve(self, product, keywords):
        raise ProviderTimeoutError("Provider timed out.")


class PartialFailureProvider(MarketDataProvider):
    provider_name = "partial failure provider"

    def retrieve(self, product, keywords):
        if product["product_name"] == "Fail Product":
            raise ProviderTimeoutError("Provider timed out for this product.")
        return market_result()


class CountingProvider(MarketDataProvider):
    provider_name = "counting provider"

    def __init__(self):
        self.calls = 0

    def retrieve(self, product, keywords):
        self.calls += 1
        return market_result()


class KeywordGenerationTests(unittest.TestCase):
    def test_expected_keyword_rules(self):
        keywords = generate_keywords(core_product())
        self.assertEqual(keywords["primary_keyword"], "ai resume builder")
        self.assertEqual(
            keywords["related_keywords"],
            [
                "ai resume builder",
                "career software",
                "ai resume builder career software",
            ],
        )
        self.assertEqual(
            keywords["search_queries"],
            [
                "ai resume builder",
                "best ai resume builder",
                "ai resume builder reviews",
                "ai resume builder career software",
            ],
        )

    def test_platform_is_not_in_market_queries(self):
        keywords = generate_keywords(core_product(platform="PartnerStack"))
        all_phrases = keywords["related_keywords"] + keywords["search_queries"]
        self.assertFalse(any("partnerstack" in phrase for phrase in all_phrases))


class ProviderTests(unittest.TestCase):
    def test_mock_results_are_deterministic(self):
        provider = MockProvider()
        product = core_product()
        keywords = generate_keywords(product)
        first = provider.retrieve(product, keywords)
        second = provider.retrieve(product, keywords)

        for field in SIGNAL_COLUMNS:
            self.assertEqual(getattr(first, field), getattr(second, field))

    def test_mock_values_are_valid(self):
        result = validate_provider_result(
            MockProvider().retrieve(
                core_product(),
                generate_keywords(core_product()),
            )
        )
        self.assertGreaterEqual(result.search_volume, 0)
        self.assertGreaterEqual(result.social_mentions_7d, 0)
        self.assertGreaterEqual(result.competitor_count, 0)
        self.assertGreaterEqual(result.days_until_peak, 0)
        self.assertGreaterEqual(result.seasonal_relevance, 0)
        self.assertLessEqual(result.seasonal_relevance, 100)

    def test_incomplete_provider_response_is_rejected(self):
        result = market_result(search_volume=None)
        with self.assertRaises(IncompleteResponseError):
            validate_provider_result(result)

    def test_session_cache_avoids_duplicate_provider_calls(self):
        provider = CountingProvider()
        products = pd.DataFrame([core_product(), core_product()])
        successful, failed = process_market_data(
            products,
            provider,
            result_cache={},
        )
        self.assertEqual(provider.calls, 1)
        self.assertEqual(len(successful), 2)
        self.assertTrue(failed.empty)


class ModeAndFallbackTests(unittest.TestCase):
    def setUp(self):
        self.manual_sample = pd.read_csv(PROJECT_DIR / "sample_products.csv")

    def test_manual_mode_rejects_missing_signal_columns(self):
        product_only = self.manual_sample.drop(columns=SIGNAL_COLUMNS)
        errors = " ".join(validate_products(product_only, mode="manual"))
        self.assertIn("Missing required columns", errors)
        self.assertIn("search_volume", errors)

    def test_automatic_mode_accepts_product_only_csv(self):
        product_only = pd.DataFrame([core_product()])
        self.assertEqual(validate_products(product_only, mode="automatic"), [])

    def test_automatic_mode_uses_valid_optional_fallback(self):
        successful, failed = process_market_data(
            self.manual_sample.head(1),
            FailingProvider(),
            result_cache={},
        )
        self.assertTrue(failed.empty)
        self.assertEqual(successful.iloc[0]["data_source"], "fallback data")
        self.assertEqual(successful.iloc[0]["retrieval_status"], "fallback")
        self.assertEqual(
            successful.iloc[0]["search_volume"],
            self.manual_sample.iloc[0]["search_volume"],
        )

    def test_automatic_mode_succeeds_without_fallback_values(self):
        product_only = pd.DataFrame([core_product()])
        successful, failed = process_market_data(
            product_only,
            SuccessfulProvider(),
            result_cache={},
        )
        self.assertTrue(failed.empty)
        self.assertEqual(len(successful), 1)
        self.assertEqual(successful.iloc[0]["data_source"], "test provider")
        ranked = score_products(successful)
        self.assertEqual(len(ranked), 1)

    def test_provider_failure_without_fallback_affects_only_one_product(self):
        products = pd.DataFrame(
            [
                core_product(product_name="Working Product"),
                core_product(product_name="Fail Product"),
            ]
        )
        successful, failed = process_market_data(
            products,
            PartialFailureProvider(),
            result_cache={},
        )
        self.assertEqual(successful["product_name"].tolist(), ["Working Product"])
        self.assertEqual(failed["product_name"].tolist(), ["Fail Product"])
        self.assertEqual(failed.iloc[0]["data_source"], "failed retrieval")
        self.assertEqual(failed.iloc[0]["retrieval_status"], "failed")

    def test_incomplete_or_invalid_fallback_does_not_reject_automatic_upload(self):
        incomplete = core_product(search_volume=50_000)
        products = pd.DataFrame([incomplete])
        self.assertEqual(validate_products(products, mode="automatic"), [])

        successful, failed = process_market_data(
            products,
            FailingProvider(),
            result_cache={},
        )
        self.assertTrue(successful.empty)
        self.assertEqual(len(failed), 1)

    def test_version_12_manual_behavior_is_unchanged(self):
        self.assertEqual(validate_products(self.manual_sample), [])
        successful, failed = process_market_data(
            self.manual_sample,
            ManualProvider(),
            result_cache={},
        )
        self.assertTrue(failed.empty)
        ranked = score_products(successful)
        direct_ranked = score_products(self.manual_sample)
        self.assertEqual(
            ranked["product_name"].tolist(),
            direct_ranked["product_name"].tolist(),
        )
        self.assertEqual(
            ranked["profit_potential_score"].tolist(),
            direct_ranked["profit_potential_score"].tolist(),
        )


if __name__ == "__main__":
    unittest.main()
