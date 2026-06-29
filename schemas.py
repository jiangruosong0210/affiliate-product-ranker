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

VIDEO_TEXT_COLUMNS = [
    "description",
    "transcript",
    "hashtags",
    "creator_name",
    "language",
]

VIDEO_ALL_COLUMNS = VIDEO_COLUMNS + VIDEO_TEXT_COLUMNS

UPLOADED_VIDEO_METADATA_COLUMNS = [
    "original_filename",
    "safe_filename",
    "file_size_bytes",
    "file_hash",
    "duration_seconds",
    "width",
    "height",
    "aspect_ratio",
    "video_orientation",
    "resolution_label",
    "frame_rate",
    "estimated_frame_count",
    "video_codec",
    "audio_track_present",
    "creation_timestamp",
    "processing_status",
    "processing_notes",
    "short_form_eligible",
]

UPLOADED_VIDEO_VISUAL_COLUMNS = [
    "sampled_frame_count",
    "sampled_timestamps",
    "average_brightness",
    "average_contrast",
    "black_frame_count",
    "duplicate_frame_count",
    "estimated_scene_change_count",
    "approximate_shot_frequency",
    "opening_frame_activity",
    "visual_analysis_status",
    "visual_analysis_notes",
]

UPLOADED_VIDEO_ASSOCIATION_COLUMNS = [
    "associated_product_id",
    "associated_product_name",
    "association_method",
    "association_status",
]
