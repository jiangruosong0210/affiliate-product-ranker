import math


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
CORE_COLUMNS = [
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
REQUIRED_COLUMNS = CORE_COLUMNS + SIGNAL_COLUMNS

TEXT_COLUMNS_REQUIRED = ["product_name", "platform", "category"]
CORE_NUMERIC_COLUMNS = ["price", "commission_rate"]
NUMERIC_COLUMNS = CORE_NUMERIC_COLUMNS + SIGNAL_COLUMNS
NON_NEGATIVE_COLUMNS = [
    "search_volume",
    "social_mentions_7d",
    "competitor_count",
    "days_until_peak",
]


def validate_products(products_df, mode="manual"):
    errors = []
    required_columns = REQUIRED_COLUMNS if mode == "manual" else CORE_COLUMNS

    missing_columns = [
        column for column in required_columns if column not in products_df.columns
    ]
    if missing_columns:
        errors.append(f"Missing required columns: {', '.join(missing_columns)}")
        return errors

    if products_df.empty:
        errors.append("The CSV file does not contain any product rows.")
        return errors

    for column in TEXT_COLUMNS_REQUIRED:
        empty_rows = products_df[
            products_df[column].isna() | (products_df[column].astype(str).str.strip() == "")
        ].index
        if len(empty_rows) > 0:
            errors.append(
                f"{column} must contain text for every product. "
                f"Problem rows: {format_row_numbers(empty_rows)}"
            )

    numeric_columns = NUMERIC_COLUMNS if mode == "manual" else CORE_NUMERIC_COLUMNS
    converted_numbers = {}
    for column in numeric_columns:
        converted = products_df[column].apply(parse_number)
        converted_numbers[column] = converted
        invalid_rows = converted[converted.isna()].index
        if len(invalid_rows) > 0:
            errors.append(
                f"{column} must contain valid numbers. "
                f"Problem rows: {format_row_numbers(invalid_rows)}"
            )

    invalid_price_rows = converted_numbers["price"][
        converted_numbers["price"] <= 0
    ].index
    if len(invalid_price_rows) > 0:
        errors.append(
            "price must be greater than 0. "
            f"Problem rows: {format_row_numbers(invalid_price_rows)}"
        )

    invalid_commission_rows = converted_numbers["commission_rate"][
        (converted_numbers["commission_rate"] < 0)
        | (converted_numbers["commission_rate"] > 1)
    ].index
    if len(invalid_commission_rows) > 0:
        errors.append(
            "commission_rate must be between 0 and 1, such as 0.20 for 20%. "
            f"Problem rows: {format_row_numbers(invalid_commission_rows)}"
        )

    if mode == "manual":
        for column in NON_NEGATIVE_COLUMNS:
            invalid_rows = converted_numbers[column][
                converted_numbers[column] < 0
            ].index
            if len(invalid_rows) > 0:
                errors.append(
                    f"{column} must be greater than or equal to 0. "
                    f"Problem rows: {format_row_numbers(invalid_rows)}"
                )

        invalid_relevance_rows = converted_numbers["seasonal_relevance"][
            (converted_numbers["seasonal_relevance"] < 0)
            | (converted_numbers["seasonal_relevance"] > 100)
        ].index
        if len(invalid_relevance_rows) > 0:
            errors.append(
                "seasonal_relevance must be between 0 and 100. "
                f"Problem rows: {format_row_numbers(invalid_relevance_rows)}"
            )

    return errors


def get_valid_fallback_signals(product):
    if any(column not in product for column in SIGNAL_COLUMNS):
        return None

    converted = {
        column: parse_number(product.get(column)) for column in SIGNAL_COLUMNS
    }
    if any(value is None for value in converted.values()):
        return None
    if any(converted[column] < 0 for column in NON_NEGATIVE_COLUMNS):
        return None
    if not 0 <= converted["seasonal_relevance"] <= 100:
        return None

    return converted


def parse_number(value):
    try:
        if isinstance(value, str):
            value = value.strip()
        if value == "":
            return None
        parsed_value = float(value)
        return parsed_value if math.isfinite(parsed_value) else None
    except (TypeError, ValueError):
        return None


def format_row_numbers(indexes):
    return ", ".join(str(index + 2) for index in indexes)


def parse_boolean(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    return None
