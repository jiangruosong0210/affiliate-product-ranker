import hashlib

from market_data.base_provider import (
    MarketDataProvider,
    MarketDataResult,
    utc_now_iso,
)


class MockProvider(MarketDataProvider):
    provider_name = "mock provider"

    def retrieve(self, product, keywords) -> MarketDataResult:
        seed_text = "|".join(
            [
                keywords["primary_keyword"],
                *keywords["related_keywords"],
                *keywords["search_queries"],
            ]
        )
        digest = hashlib.sha256(seed_text.encode("utf-8")).digest()

        return MarketDataResult(
            search_volume=5_000 + integer_from(digest, 0, 4) % 95_001,
            search_growth_7d=-50 + integer_from(digest, 4, 8) % 101,
            social_mentions_7d=integer_from(digest, 8, 12) % 10_001,
            competitor_count=integer_from(digest, 12, 16) % 101,
            days_until_peak=integer_from(digest, 16, 20) % 61,
            seasonal_relevance=integer_from(digest, 20, 24) % 101,
            data_source="mock provider",
            retrieved_at=utc_now_iso(),
            confidence_level="not assessed",
            retrieval_status="success",
            error_message="",
        )


def integer_from(digest: bytes, start: int, end: int) -> int:
    return int.from_bytes(digest[start:end], byteorder="big")
