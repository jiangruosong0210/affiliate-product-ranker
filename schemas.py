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

VIDEO_COLUMNS = [
    "video_id",
    "product_id",
    "platform",
    "title",
    "video_url",
    "publish_date",
    "duration_seconds",
    "views",
    "likes",
    "comments",
    "shares",
    "creator_followers",
    "content_format",
    "hook_type",
    "demo_present",
    "comparison_present",
    "cta_present",
    "main_feature",
]

VIDEO_PLATFORMS = ["YouTube", "TikTok", "Instagram", "Facebook", "Other"]
VIDEO_CONTENT_FORMATS = [
    "demo",
    "review",
    "comparison",
    "unboxing",
    "tutorial",
    "testimonial",
    "lifestyle",
    "listicle",
    "other",
]
VIDEO_HOOK_TYPES = [
    "result_first",
    "problem_solution",
    "question",
    "surprising_fact",
    "discount_offer",
    "general_introduction",
    "other",
]
VIDEO_BOOLEAN_COLUMNS = [
    "demo_present",
    "comparison_present",
    "cta_present",
]
VIDEO_OPTIONAL_COUNT_COLUMNS = [
    "likes",
    "comments",
    "shares",
    "creator_followers",
]
