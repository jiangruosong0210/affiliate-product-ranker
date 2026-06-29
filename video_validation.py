import re

import pandas as pd

from schemas import (
    VIDEO_BOOLEAN_COLUMNS,
    VIDEO_TEXT_COLUMNS,
    VIDEO_COLUMNS,
    VIDEO_CONTENT_FORMATS,
    VIDEO_HOOK_TYPES,
    VIDEO_OPTIONAL_COUNT_COLUMNS,
    VIDEO_PLATFORMS,
)
from validation import parse_boolean, parse_number


REQUIRED_VIDEO_FIELDS = [
    "video_id",
    "product_id",
    "platform",
    "publish_date",
    "duration_seconds",
    "views",
    "content_format",
    "hook_type",
]
COUNT_COLUMNS = ["views", *VIDEO_OPTIONAL_COUNT_COLUMNS]


def validate_video_records(videos_df, valid_product_ids):
    missing_columns = [
        column for column in VIDEO_COLUMNS if column not in videos_df.columns
    ]
    if missing_columns:
        excluded = videos_df.copy()
        excluded["exclusion_reasons"] = (
            f"Missing required columns: {', '.join(missing_columns)}"
        )
        excluded["source_row"] = excluded.index + 2
        return pd.DataFrame(), excluded, pd.DataFrame()

    cleaned = videos_df.astype(object).copy()
    for column in VIDEO_TEXT_COLUMNS:
        if column not in cleaned.columns:
            cleaned[column] = ""
    errors = {index: [] for index in cleaned.index}
    warnings = {index: [] for index in cleaned.index}
    duplicate_mask = cleaned["video_id"].duplicated(keep=False)
    platform_lookup = {value.lower(): value for value in VIDEO_PLATFORMS}

    for index, row in cleaned.iterrows():
        for column in REQUIRED_VIDEO_FIELDS:
            if is_blank(row.get(column)):
                errors[index].append(f"{column} must be non-empty")

        if duplicate_mask.loc[index]:
            errors[index].append("duplicate video_id")
        if row.get("product_id") not in valid_product_ids:
            errors[index].append(
                "orphan video: product_id does not match a valid product"
            )

        platform_key = normalize_category(row.get("platform"))
        if platform_key not in platform_lookup:
            errors[index].append("invalid platform")
        else:
            cleaned.at[index, "platform"] = platform_lookup[platform_key]

        content_format = normalize_category(row.get("content_format"))
        if content_format not in VIDEO_CONTENT_FORMATS:
            errors[index].append("invalid content_format")
        else:
            cleaned.at[index, "content_format"] = content_format

        hook_type = normalize_category(row.get("hook_type"))
        if hook_type not in VIDEO_HOOK_TYPES:
            errors[index].append("invalid hook_type")
        else:
            cleaned.at[index, "hook_type"] = hook_type

        publish_date = pd.to_datetime(row.get("publish_date"), errors="coerce")
        if pd.isna(publish_date):
            errors[index].append("publish_date must be parseable")
        else:
            cleaned.at[index, "publish_date"] = publish_date.date().isoformat()

        duration = parse_number(row.get("duration_seconds"))
        if duration is None or duration <= 0:
            errors[index].append("duration_seconds must be greater than 0")
        else:
            cleaned.at[index, "duration_seconds"] = duration

        for column in COUNT_COLUMNS:
            value = row.get(column)
            if column in VIDEO_OPTIONAL_COUNT_COLUMNS and is_blank(value):
                cleaned.at[index, column] = pd.NA
                continue
            parsed = parse_non_negative_integer(value)
            if parsed is None:
                errors[index].append(
                    f"{column} must be a non-negative whole number"
                )
            else:
                cleaned.at[index, column] = parsed

        for column in VIDEO_BOOLEAN_COLUMNS:
            value = row.get(column)
            if is_blank(value):
                cleaned.at[index, column] = pd.NA
                continue
            parsed = parse_boolean(value)
            if parsed is None:
                errors[index].append(f"{column} must be a valid boolean")
            else:
                cleaned.at[index, column] = parsed

        cleaned.at[index, "title"] = normalize_optional_text(row.get("title"))
        cleaned.at[index, "main_feature"] = normalize_optional_text(
            row.get("main_feature"),
            lowercase=True,
        )
        cleaned.at[index, "video_url"] = normalize_optional_text(
            row.get("video_url")
        )
        for column in VIDEO_TEXT_COLUMNS:
            cleaned.at[index, column] = normalize_optional_text(row.get(column))

        video_url = cleaned.at[index, "video_url"]
        if video_url and not re.match(r"^https?://", video_url, re.IGNORECASE):
            warnings[index].append("video_url does not begin with http:// or https://")

        views = cleaned.at[index, "views"]
        if isinstance(views, int):
            for column in ["likes", "comments", "shares"]:
                interaction = cleaned.at[index, column]
                if (
                    not pd.isna(interaction)
                    and isinstance(interaction, int)
                    and interaction > views
                ):
                    warnings[index].append(f"{column} exceeds views")

    valid_indexes = [index for index, values in errors.items() if not values]
    excluded_indexes = [index for index, values in errors.items() if values]

    valid = cleaned.loc[valid_indexes].copy().reset_index(drop=True)
    excluded = videos_df.loc[excluded_indexes].copy()
    if not excluded.empty:
        excluded["exclusion_reasons"] = [
            "; ".join(errors[index]) for index in excluded.index
        ]
        excluded["source_row"] = excluded.index + 2
        excluded = excluded.reset_index(drop=True)

    warning_indexes = [
        index for index in valid_indexes if warnings[index]
    ]
    warning_report = cleaned.loc[warning_indexes].copy()
    if not warning_report.empty:
        warning_report["warning_reasons"] = [
            "; ".join(warnings[index]) for index in warning_report.index
        ]
        warning_report["source_row"] = warning_report.index + 2
        warning_report = warning_report.reset_index(drop=True)

    return valid, excluded, warning_report


def parse_non_negative_integer(value):
    parsed = parse_number(value)
    if parsed is None or parsed < 0 or not float(parsed).is_integer():
        return None
    return int(parsed)


def normalize_category(value):
    return "" if is_blank(value) else str(value).strip().lower()


def normalize_optional_text(value, lowercase=False):
    if is_blank(value):
        return ""
    text = " ".join(str(value).strip().split())
    return text.lower() if lowercase else text


def is_blank(value):
    return pd.isna(value) or str(value).strip() == ""
