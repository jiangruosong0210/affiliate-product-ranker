REQUIRED_COLUMNS = [
    "product_name",
    "platform",
    "category",
    "price",
    "commission_rate",
    "trend_score",
    "demand_score",
    "competition_score",
    "urgency_score",
    "product_url",
]

TEXT_COLUMNS_REQUIRED = ["product_name", "platform", "category"]
NUMERIC_COLUMNS = [
    "price",
    "commission_rate",
    "trend_score",
    "demand_score",
    "competition_score",
    "urgency_score",
]
SCORE_COLUMNS = ["trend_score", "demand_score", "competition_score", "urgency_score"]


def validate_products(products_df):
    errors = []

    missing_columns = [
        column for column in REQUIRED_COLUMNS if column not in products_df.columns
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

    converted_numbers = {}
    has_numeric_parse_errors = False
    for column in NUMERIC_COLUMNS:
        converted = products_df[column].apply(parse_number)
        converted_numbers[column] = converted
        invalid_rows = converted[converted.isna()].index
        if len(invalid_rows) > 0:
            has_numeric_parse_errors = True
            errors.append(
                f"{column} must contain valid numbers. "
                f"Problem rows: {format_row_numbers(invalid_rows)}"
            )

    if has_numeric_parse_errors:
        return errors

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

    for column in SCORE_COLUMNS:
        invalid_score_rows = converted_numbers[column][
            (converted_numbers[column] < 0) | (converted_numbers[column] > 100)
        ].index
        if len(invalid_score_rows) > 0:
            errors.append(
                f"{column} must be between 0 and 100. "
                f"Problem rows: {format_row_numbers(invalid_score_rows)}"
            )

    return errors


def parse_number(value):
    try:
        if isinstance(value, str):
            value = value.strip()
        if value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def format_row_numbers(indexes):
    return ", ".join(str(index + 2) for index in indexes)
