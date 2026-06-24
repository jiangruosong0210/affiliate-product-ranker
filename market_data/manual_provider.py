from market_data.base_provider import (
    SIGNAL_FIELDS,
    MarketDataProvider,
    MarketDataResult,
    utc_now_iso,
)


class ManualProvider(MarketDataProvider):
    provider_name = "uploaded CSV"
    use_cache = False

    def retrieve(self, product, keywords) -> MarketDataResult:
        signals = {field: product[field] for field in SIGNAL_FIELDS}
        return MarketDataResult(
            **signals,
            data_source="uploaded CSV",
            retrieved_at=utc_now_iso(),
            confidence_level="not assessed",
            retrieval_status="success",
            error_message="",
        )
