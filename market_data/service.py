from copy import deepcopy

import pandas as pd

from keyword_generation import generate_keywords
from market_data.base_provider import (
    SIGNAL_FIELDS,
    MarketDataResult,
    ProviderError,
    utc_now_iso,
    validate_provider_result,
)
from validation import get_valid_fallback_signals


def process_market_data(products_df, provider, result_cache=None):
    successful_rows = []
    failed_rows = []
    cache = result_cache if result_cache is not None else {}

    for _, product_row in products_df.iterrows():
        product = product_row.to_dict()
        keywords = generate_keywords(product)
        keyword_columns = serialize_keywords(keywords)

        try:
            result = retrieve_with_cache(provider, product, keywords, cache)
            merged = merge_product_result(product, result, keyword_columns)
            successful_rows.append(merged)
        except Exception as exc:
            fallback_signals = get_valid_fallback_signals(product)
            if fallback_signals is not None:
                fallback_result = MarketDataResult(
                    **fallback_signals,
                    data_source="fallback data",
                    retrieved_at=utc_now_iso(),
                    confidence_level="not assessed",
                    retrieval_status="fallback",
                    error_message=safe_error_message(exc),
                )
                successful_rows.append(
                    merge_product_result(product, fallback_result, keyword_columns)
                )
            else:
                failed_rows.append(
                    {
                        **core_product_values(product),
                        **keyword_columns,
                        **{field: None for field in SIGNAL_FIELDS},
                        "data_source": "failed retrieval",
                        "retrieved_at": utc_now_iso(),
                        "confidence_level": "not assessed",
                        "retrieval_status": "failed",
                        "error_message": safe_error_message(exc),
                    }
                )

    return pd.DataFrame(successful_rows), pd.DataFrame(failed_rows)


def retrieve_with_cache(provider, product, keywords, cache):
    if not provider.use_cache:
        return validate_provider_result(provider.retrieve(product, keywords))

    cache_key = provider.cache_key(product, keywords)
    if cache_key not in cache:
        result = provider.retrieve(product, keywords)
        validated_result = validate_provider_result(result)
        if validated_result.retrieval_status != "success":
            raise ProviderError(
                validated_result.error_message or "Provider retrieval was unsuccessful."
            )
        cache[cache_key] = validated_result
    return deepcopy(cache[cache_key])


def merge_product_result(product, result, keyword_columns):
    return {
        **core_product_values(product),
        **keyword_columns,
        **result.to_dict(),
    }


def core_product_values(product):
    return {
        "product_id": product.get("product_id", ""),
        "product_name": product.get("product_name"),
        "category": product.get("category"),
        "product_type": product.get("product_type", ""),
        "price": product.get("reference_price", product.get("price")),
        "commission_rate": product.get(
            "reference_commission_rate",
            product.get("commission_rate"),
        ),
        "reference_price": product.get("reference_price", product.get("price")),
        "reference_commission_rate": product.get(
            "reference_commission_rate",
            product.get("commission_rate"),
        ),
        "product_url": product.get("product_url", ""),
    }


def serialize_keywords(keywords):
    return {
        "primary_keyword": keywords["primary_keyword"],
        "related_keywords": "; ".join(keywords["related_keywords"]),
        "search_queries": "; ".join(keywords["search_queries"]),
    }


def safe_error_message(error):
    if isinstance(error, ProviderError):
        return str(error)
    return "Provider retrieval failed because of an unexpected provider error."
