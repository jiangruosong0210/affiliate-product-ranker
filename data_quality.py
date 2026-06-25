import pandas as pd

from schemas import OFFER_COLUMNS, PRODUCT_CORE_COLUMNS, SIGNAL_COLUMNS
from validation import (
    parse_boolean,
    parse_number,
)


def validate_product_records(products_df, mode="manual"):
    required = (
        PRODUCT_CORE_COLUMNS + SIGNAL_COLUMNS
        if mode == "manual"
        else PRODUCT_CORE_COLUMNS
    )
    missing = [column for column in required if column not in products_df.columns]
    if missing:
        return (
            pd.DataFrame(),
            dataframe_error(products_df, f"Missing required columns: {', '.join(missing)}"),
        )

    reasons = {index: [] for index in products_df.index}
    duplicate_mask = products_df["product_id"].duplicated(keep=False)

    for index, row in products_df.iterrows():
        for column in ["product_id", "product_name", "category", "product_type"]:
            if is_blank(row.get(column)):
                reasons[index].append(f"{column} must be non-empty")
        if duplicate_mask.loc[index]:
            reasons[index].append("duplicate product_id")

        price = parse_number(row.get("reference_price"))
        rate = parse_number(row.get("reference_commission_rate"))
        if price is None or price <= 0:
            reasons[index].append("reference_price must be greater than 0")
        if rate is None or not 0 <= rate <= 1:
            reasons[index].append(
                "reference_commission_rate must be between 0 and 1"
            )

        if mode == "manual":
            validate_signal_values(row, reasons[index])

    return split_records(products_df, reasons)


def validate_offer_records(offers_df, valid_product_ids):
    missing = [column for column in OFFER_COLUMNS if column not in offers_df.columns]
    if missing:
        return (
            pd.DataFrame(),
            dataframe_error(offers_df, f"Missing required columns: {', '.join(missing)}"),
        )

    reasons = {index: [] for index in offers_df.index}
    duplicate_mask = offers_df["offer_id"].duplicated(keep=False)
    valid_payouts = {"one_time", "recurring", "fixed_amount", "lead"}
    valid_statuses = {"active", "inactive", "unknown"}

    for index, row in offers_df.iterrows():
        for column in ["offer_id", "product_id", "platform", "payout_type", "offer_status"]:
            if is_blank(row.get(column)):
                reasons[index].append(f"{column} must be non-empty")
        if duplicate_mask.loc[index]:
            reasons[index].append("duplicate offer_id")
        if row.get("product_id") not in valid_product_ids:
            reasons[index].append("orphan offer: product_id does not match a valid product")

        payout_type = row.get("payout_type")
        if payout_type not in valid_payouts:
            reasons[index].append("invalid payout_type")

        status = row.get("offer_status")
        if status not in valid_statuses:
            reasons[index].append("invalid offer_status")

        cookie = parse_number(row.get("cookie_duration_days"))
        if cookie is None or cookie < 0:
            reasons[index].append("cookie_duration_days must be non-negative")

        recurring = parse_boolean(row.get("recurring_commission"))
        if recurring is None:
            reasons[index].append("recurring_commission must be a valid boolean")
        elif payout_type == "recurring" and not recurring:
            reasons[index].append(
                "recurring payout_type requires recurring_commission=true"
            )
        elif payout_type in {"one_time", "fixed_amount", "lead"} and recurring:
            reasons[index].append(
                "non-recurring payout_type requires recurring_commission=false"
            )

        if payout_type in {"one_time", "recurring"}:
            offer_price = parse_number(row.get("offer_price"))
            commission_rate = parse_number(row.get("commission_rate"))
            if offer_price is None or offer_price <= 0:
                reasons[index].append(
                    "percentage payout requires offer_price greater than 0"
                )
            if commission_rate is None or not 0 < commission_rate <= 1:
                reasons[index].append(
                    "percentage payout requires 0 < commission_rate <= 1"
                )
        elif payout_type == "fixed_amount":
            fixed_amount = parse_number(row.get("fixed_commission_amount"))
            if fixed_amount is None or fixed_amount <= 0:
                reasons[index].append(
                    "fixed_amount payout requires fixed_commission_amount greater than 0"
                )
        elif payout_type == "lead":
            lead_amount = parse_number(row.get("commission_per_lead"))
            if lead_amount is None or lead_amount <= 0:
                reasons[index].append(
                    "lead payout requires commission_per_lead greater than 0"
                )

    valid, excluded = split_records(offers_df, reasons)
    if not valid.empty:
        valid["recurring_commission"] = valid["recurring_commission"].apply(
            parse_boolean
        )
    return valid, excluded


def validate_signal_values(row, reasons):
    non_negative = [
        "search_volume",
        "social_mentions_7d",
        "competitor_count",
        "days_until_peak",
    ]
    for column in SIGNAL_COLUMNS:
        if parse_number(row.get(column)) is None:
            reasons.append(f"{column} must contain a valid number")
    for column in non_negative:
        value = parse_number(row.get(column))
        if value is not None and value < 0:
            reasons.append(f"{column} must be non-negative")
    relevance = parse_number(row.get("seasonal_relevance"))
    if relevance is not None and not 0 <= relevance <= 100:
        reasons.append("seasonal_relevance must be between 0 and 100")


def split_records(dataframe, reasons):
    valid_indexes = [index for index, values in reasons.items() if not values]
    excluded_indexes = [index for index, values in reasons.items() if values]

    valid = dataframe.loc[valid_indexes].copy().reset_index(drop=True)
    excluded = dataframe.loc[excluded_indexes].copy()
    if not excluded.empty:
        excluded["exclusion_reasons"] = [
            "; ".join(reasons[index]) for index in excluded.index
        ]
        excluded["source_row"] = excluded.index + 2
        excluded = excluded.reset_index(drop=True)
    return valid, excluded


def dataframe_error(dataframe, message):
    result = dataframe.copy()
    result["exclusion_reasons"] = message
    result["source_row"] = result.index + 2
    return result


def is_blank(value):
    return pd.isna(value) or str(value).strip() == ""
