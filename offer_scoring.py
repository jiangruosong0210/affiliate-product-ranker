import pandas as pd


OFFER_SCORING_CONFIG = {
    "caps": {
        "commission_value": 100,
        "commission_rate": 0.50,
        "cookie_duration_days": 90,
    },
    "percentage_weights": {
        "commission_value": 0.40,
        "commission_rate": 0.20,
        "cookie_duration": 0.15,
        "recurring_commission": 0.15,
        "offer_status": 0.10,
    },
    "fixed_lead_weights": {
        "commission_value": 0.6153846153846154,
        "cookie_duration": 0.23076923076923078,
        "offer_status": 0.15384615384615385,
    },
}


def score_offers(offers_df: pd.DataFrame) -> pd.DataFrame:
    scored = offers_df.copy()
    caps = OFFER_SCORING_CONFIG["caps"]

    scored["commission_value"] = scored.apply(calculate_commission_value, axis=1)
    scored["commission_value_score"] = (
        scored["commission_value"] / caps["commission_value"] * 100
    ).clip(0, 100)
    scored["commission_rate_score"] = (
        pd.to_numeric(scored["commission_rate"], errors="coerce")
        / caps["commission_rate"]
        * 100
    ).clip(0, 100)
    scored["cookie_duration_score"] = (
        pd.to_numeric(scored["cookie_duration_days"])
        / caps["cookie_duration_days"]
        * 100
    ).clip(0, 100)
    scored["recurring_score"] = scored["recurring_commission"].map(
        {True: 100.0, False: 0.0}
    )
    scored["status_score"] = scored["offer_status"].map(
        {"active": 100.0, "unknown": 50.0, "inactive": 0.0}
    )

    contribution_rows = scored.apply(calculate_contributions, axis=1)
    contribution_df = pd.DataFrame(contribution_rows.tolist(), index=scored.index)
    scored = pd.concat([scored, contribution_df], axis=1)
    contribution_columns = [
        "commission_value_contribution",
        "commission_rate_contribution",
        "cookie_duration_contribution",
        "recurring_contribution",
        "status_contribution",
    ]
    scored["platform_offer_score"] = scored[contribution_columns].sum(axis=1)

    rounded_columns = [
        "commission_value",
        "commission_value_score",
        "commission_rate_score",
        "cookie_duration_score",
        "recurring_score",
        "status_score",
        "platform_offer_score",
        *contribution_columns,
    ]
    for column in rounded_columns:
        scored[column] = scored[column].round(2)

    explanations = scored.apply(explain_offer, axis=1)
    scored["strengths"] = explanations.map(lambda item: item[0])
    scored["risks"] = explanations.map(lambda item: item[1])
    scored["recommended_action"] = explanations.map(lambda item: item[2])
    scored["recommended_offer"] = False
    scored["recommendation_warning"] = ""

    for product_id, group in scored.groupby("product_id", sort=False):
        active = group[group["offer_status"] == "active"]
        eligible = active
        warning = ""
        if eligible.empty:
            eligible = group[group["offer_status"] == "unknown"]
            warning = "No active offer is available; verify this unknown offer."
        if eligible.empty:
            continue

        recommended_index = eligible.sort_values(
            by=[
                "platform_offer_score",
                "commission_value",
                "cookie_duration_days",
                "offer_id",
            ],
            ascending=[False, False, False, True],
        ).index[0]
        scored.loc[recommended_index, "recommended_offer"] = True
        scored.loc[recommended_index, "recommendation_warning"] = warning

    return scored.sort_values(
        by=["product_id", "platform_offer_score"],
        ascending=[True, False],
    ).reset_index(drop=True)


def calculate_commission_value(row) -> float:
    payout_type = row["payout_type"]
    if payout_type in {"one_time", "recurring"}:
        return float(row["offer_price"]) * float(row["commission_rate"])
    if payout_type == "fixed_amount":
        return float(row["fixed_commission_amount"])
    return float(row["commission_per_lead"])


def calculate_contributions(row) -> dict:
    empty = {
        "commission_value_contribution": 0.0,
        "commission_rate_contribution": 0.0,
        "cookie_duration_contribution": 0.0,
        "recurring_contribution": 0.0,
        "status_contribution": 0.0,
    }

    if row["payout_type"] in {"one_time", "recurring"}:
        weights = OFFER_SCORING_CONFIG["percentage_weights"]
        empty.update(
            {
                "commission_value_contribution": (
                    row["commission_value_score"] * weights["commission_value"]
                ),
                "commission_rate_contribution": (
                    row["commission_rate_score"] * weights["commission_rate"]
                ),
                "cookie_duration_contribution": (
                    row["cookie_duration_score"] * weights["cookie_duration"]
                ),
                "recurring_contribution": (
                    row["recurring_score"] * weights["recurring_commission"]
                ),
                "status_contribution": (
                    row["status_score"] * weights["offer_status"]
                ),
            }
        )
    else:
        weights = OFFER_SCORING_CONFIG["fixed_lead_weights"]
        empty.update(
            {
                "commission_value_contribution": (
                    row["commission_value_score"] * weights["commission_value"]
                ),
                "cookie_duration_contribution": (
                    row["cookie_duration_score"] * weights["cookie_duration"]
                ),
                "status_contribution": (
                    row["status_score"] * weights["offer_status"]
                ),
            }
        )

    return empty


def explain_offer(row) -> tuple[str, str, str]:
    strengths = []
    if row["commission_value_score"] >= 60:
        strengths.append("strong commission value")
    if row["cookie_duration_score"] >= 50:
        strengths.append("useful cookie duration")
    if row["payout_type"] == "recurring":
        strengths.append("recurring commission")
    if row["offer_status"] == "active":
        strengths.append("active availability")
    if not strengths:
        strengths.append("a valid platform offer")

    risks = []
    if row["commission_value_score"] < 30:
        risks.append("low commission value")
    if row["cookie_duration_days"] < 7:
        risks.append("short cookie duration")
    if row["offer_status"] == "unknown":
        risks.append("availability is unknown")
    if row["offer_status"] == "inactive":
        risks.append("offer is inactive")
    if not risks:
        risks.append("no major offer risk stands out")

    if row["offer_status"] == "inactive":
        action = "Do not promote unless the offer becomes active"
    elif row["offer_status"] == "unknown":
        action = "Verify availability and terms before promotion"
    elif row["platform_offer_score"] >= 65:
        action = "Prioritize this offer for an initial campaign test"
    else:
        action = "Compare against other active offers before promoting"

    return "; ".join(strengths), "; ".join(risks), action
