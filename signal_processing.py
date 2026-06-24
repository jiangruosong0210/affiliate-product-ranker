import pandas as pd


SIGNAL_CONFIG = {
    "max_search_volume": 100_000,
    "max_social_mentions": 10_000,
    "max_competitor_count": 100,
    "max_positive_growth": 50,
    "max_negative_growth": -50,
    "max_days_until_peak": 60,
    "max_commission_per_sale": 50,
    "demand_weights": {
        "search_volume": 0.70,
        "social_mentions": 0.30,
    },
    "urgency_weights": {
        "timing": 0.60,
        "seasonal_relevance": 0.40,
    },
}


RAW_NUMERIC_COLUMNS = [
    "price",
    "commission_rate",
    "search_volume",
    "search_growth_7d",
    "social_mentions_7d",
    "competitor_count",
    "days_until_peak",
    "seasonal_relevance",
]


def capped_score(values: pd.Series, maximum: float) -> pd.Series:
    return (values / maximum * 100).clip(lower=0, upper=100)


def process_signals(products_df: pd.DataFrame) -> pd.DataFrame:
    processed_df = products_df.copy()

    for column in RAW_NUMERIC_COLUMNS:
        processed_df[column] = pd.to_numeric(processed_df[column])

    processed_df["commission_per_sale"] = (
        processed_df["price"] * processed_df["commission_rate"]
    )
    processed_df["commission_score"] = capped_score(
        processed_df["commission_per_sale"],
        SIGNAL_CONFIG["max_commission_per_sale"],
    )

    processed_df["search_volume_score"] = capped_score(
        processed_df["search_volume"],
        SIGNAL_CONFIG["max_search_volume"],
    )
    processed_df["social_mentions_score"] = capped_score(
        processed_df["social_mentions_7d"],
        SIGNAL_CONFIG["max_social_mentions"],
    )

    demand_weights = SIGNAL_CONFIG["demand_weights"]
    processed_df["demand_score"] = (
        processed_df["search_volume_score"] * demand_weights["search_volume"]
        + processed_df["social_mentions_score"] * demand_weights["social_mentions"]
    )

    growth_range = (
        SIGNAL_CONFIG["max_positive_growth"]
        - SIGNAL_CONFIG["max_negative_growth"]
    )
    processed_df["trend_score"] = (
        (
            processed_df["search_growth_7d"]
            - SIGNAL_CONFIG["max_negative_growth"]
        )
        / growth_range
        * 100
    ).clip(lower=0, upper=100)

    processed_df["competition_score"] = capped_score(
        processed_df["competitor_count"],
        SIGNAL_CONFIG["max_competitor_count"],
    )
    processed_df["competition_opportunity"] = (
        100 - processed_df["competition_score"]
    )

    processed_df["timing_urgency_score"] = (
        100
        - (
            processed_df["days_until_peak"]
            / SIGNAL_CONFIG["max_days_until_peak"]
            * 100
        )
    ).clip(lower=0, upper=100)
    urgency_weights = SIGNAL_CONFIG["urgency_weights"]
    processed_df["urgency_score"] = (
        processed_df["timing_urgency_score"] * urgency_weights["timing"]
        + processed_df["seasonal_relevance"]
        * urgency_weights["seasonal_relevance"]
    )

    return processed_df
