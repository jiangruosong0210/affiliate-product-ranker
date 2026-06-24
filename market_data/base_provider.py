import math
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime, timezone


SIGNAL_FIELDS = [
    "search_volume",
    "search_growth_7d",
    "social_mentions_7d",
    "competitor_count",
    "days_until_peak",
    "seasonal_relevance",
]
VALID_STATUSES = {"success", "fallback", "failed"}
VALID_CONFIDENCE_LEVELS = {"low", "medium", "high", "not assessed"}


class ProviderError(Exception):
    pass


class MissingCredentialsError(ProviderError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


class IncompleteResponseError(ProviderError):
    pass


class InvalidProviderDataError(ProviderError):
    pass


class RateLimitError(ProviderError):
    pass


@dataclass
class MarketDataResult:
    search_volume: float | None
    search_growth_7d: float | None
    social_mentions_7d: float | None
    competitor_count: float | None
    days_until_peak: float | None
    seasonal_relevance: float | None
    data_source: str
    retrieved_at: str
    confidence_level: str
    retrieval_status: str
    error_message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class MarketDataProvider(ABC):
    provider_name = "base provider"
    use_cache = True

    @abstractmethod
    def retrieve(self, product, keywords) -> MarketDataResult:
        raise NotImplementedError

    def cache_key(self, product, keywords) -> str:
        related = "|".join(keywords["related_keywords"])
        queries = "|".join(keywords["search_queries"])
        return f"{self.provider_name}:{keywords['primary_keyword']}:{related}:{queries}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def validate_provider_result(result: MarketDataResult) -> MarketDataResult:
    if not isinstance(result, MarketDataResult):
        raise InvalidProviderDataError(
            "Provider returned an unexpected response type."
        )

    missing_fields = [
        field for field in SIGNAL_FIELDS if getattr(result, field) is None
    ]
    if missing_fields:
        raise IncompleteResponseError(
            f"Provider response is missing: {', '.join(missing_fields)}."
        )

    converted = {}
    for field in SIGNAL_FIELDS:
        try:
            value = float(getattr(result, field))
        except (TypeError, ValueError) as exc:
            raise InvalidProviderDataError(
                f"Provider returned a non-numeric value for {field}."
            ) from exc
        if not math.isfinite(value):
            raise InvalidProviderDataError(
                f"Provider returned an invalid value for {field}."
            )
        converted[field] = value

    non_negative_fields = [
        "search_volume",
        "social_mentions_7d",
        "competitor_count",
        "days_until_peak",
    ]
    for field in non_negative_fields:
        if converted[field] < 0:
            raise InvalidProviderDataError(
                f"Provider returned a negative value for {field}."
            )

    if not 0 <= converted["seasonal_relevance"] <= 100:
        raise InvalidProviderDataError(
            "Provider returned seasonal_relevance outside 0-100."
        )
    if not result.data_source.strip():
        raise InvalidProviderDataError("Provider did not identify its data source.")
    if not result.retrieved_at.strip():
        raise InvalidProviderDataError("Provider did not provide a retrieval time.")
    if result.confidence_level not in VALID_CONFIDENCE_LEVELS:
        raise InvalidProviderDataError("Provider returned an invalid confidence level.")
    if result.retrieval_status not in VALID_STATUSES:
        raise InvalidProviderDataError("Provider returned an invalid retrieval status.")

    for field, value in converted.items():
        setattr(result, field, value)

    return result
