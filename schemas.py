PRODUCT_CORE_COLUMNS = [
    "product_id",
    "product_name",
    "category",
    "product_type",
    "product_url",
    "reference_price",
    "reference_commission_rate",
]

OFFER_COLUMNS = [
    "offer_id",
    "product_id",
    "platform",
    "payout_type",
    "offer_price",
    "commission_rate",
    "fixed_commission_amount",
    "commission_per_lead",
    "cookie_duration_days",
    "recurring_commission",
    "affiliate_url",
    "offer_status",
]

LEGACY_CORE_COLUMNS = [
    "product_name",
    "platform",
    "category",
    "price",
    "commission_rate",
    "product_url",
]

SIGNAL_COLUMNS = [
    "search_volume",
    "search_growth_7d",
    "social_mentions_7d",
    "competitor_count",
    "days_until_peak",
    "seasonal_relevance",
]

LEGACY_REQUIRED_COLUMNS = LEGACY_CORE_COLUMNS + SIGNAL_COLUMNS
