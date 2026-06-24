import pandas as pd

from signal_processing import process_signals


SCORING_CONFIG = {
    "weights": {
        "commission": 0.30,
        "trend": 0.25,
        "demand": 0.20,
        "competition": 0.15,
        "urgency": 0.10,
    },
    "contribution_columns": {
        "commission": "commission_contribution",
        "trend": "trend_contribution",
        "demand": "demand_contribution",
        "competition": "competition_contribution",
        "urgency": "urgency_contribution",
    },
}


def score_products(products_df: pd.DataFrame) -> pd.DataFrame:
    ranked_df = process_signals(products_df)
    weights = SCORING_CONFIG["weights"]

    ranked_df["commission_contribution"] = (
        ranked_df["commission_score"] * weights["commission"]
    )
    ranked_df["trend_contribution"] = ranked_df["trend_score"] * weights["trend"]
    ranked_df["demand_contribution"] = ranked_df["demand_score"] * weights["demand"]
    ranked_df["competition_contribution"] = (
        ranked_df["competition_opportunity"] * weights["competition"]
    )
    ranked_df["urgency_contribution"] = (
        ranked_df["urgency_score"] * weights["urgency"]
    )

    contribution_columns = list(SCORING_CONFIG["contribution_columns"].values())
    ranked_df["profit_potential_score"] = ranked_df[contribution_columns].sum(axis=1)

    rounded_columns = [
        "commission_per_sale",
        "commission_score",
        "search_volume_score",
        "social_mentions_score",
        "trend_score",
        "demand_score",
        "competition_score",
        "competition_opportunity",
        "timing_urgency_score",
        "urgency_score",
        "profit_potential_score",
        *contribution_columns,
    ]
    for column in rounded_columns:
        ranked_df[column] = ranked_df[column].round(2)

    ranked_df["explanation"] = ranked_df.apply(generate_explanation, axis=1)
    ranked_df = ranked_df.sort_values(
        by="profit_potential_score", ascending=False
    ).reset_index(drop=True)
    ranked_df.insert(0, "rank", ranked_df.index + 1)

    return ranked_df


def generate_explanation(row: pd.Series) -> str:
    factors = [
        ("commission_contribution", commission_strength(row)),
        ("trend_contribution", trend_strength(row)),
        ("demand_contribution", demand_strength(row)),
        ("competition_contribution", "lower competition"),
        ("urgency_contribution", urgency_strength(row)),
    ]
    sorted_factors = sorted(factors, key=lambda item: row[item[0]], reverse=True)
    strongest = [label for column, label in sorted_factors if row[column] > 0][:3]

    if len(strongest) >= 3:
        strengths = f"{strongest[0]}, {strongest[1]}, and {strongest[2]}"
    elif len(strongest) == 2:
        strengths = f"{strongest[0]} and {strongest[1]}"
    elif len(strongest) == 1:
        strengths = strongest[0]
    else:
        strengths = "no clear strength"

    weakness = find_meaningful_weakness(row)
    risk = weakness if weakness else "no major weakness stands out"
    action = recommend_action(row, weakness)

    return f"Strengths: {strengths}. Risk: {risk}. Action: {action}."


def find_meaningful_weakness(row: pd.Series) -> str:
    weaknesses = []

    if row["competition_score"] >= 75:
        weaknesses.append(("high competition", row["competition_contribution"]))
    if row["urgency_score"] <= 35:
        weaknesses.append(("weak short-term urgency", row["urgency_contribution"]))
    if row["trend_score"] <= 35:
        weaknesses.append(("a weak current trend", row["trend_contribution"]))
    if row["demand_score"] <= 35:
        weaknesses.append(("weak buyer demand", row["demand_contribution"]))
    if row["commission_score"] <= 35:
        weaknesses.append(
            ("low commission per sale", row["commission_contribution"])
        )

    if not weaknesses:
        return ""

    return min(weaknesses, key=lambda item: item[1])[0]


def recommend_action(row: pd.Series, weakness: str) -> str:
    score = row["profit_potential_score"]

    if row["search_growth_7d"] > 10 and row["days_until_peak"] <= 14:
        return "Test promotion during the next two weeks while momentum is increasing"
    if score >= 70 and not weakness:
        return "Prioritize this product for a short-term campaign test"
    if score >= 60:
        return "Test with a small campaign before scaling"
    if score >= 45:
        return "Keep as a backup option and compare against stronger products"
    return "Do not prioritize yet unless you have a specific audience fit"


def commission_strength(row: pd.Series) -> str:
    return f"good commission potential (${row['commission_per_sale']:.2f} per sale)"


def trend_strength(row: pd.Series) -> str:
    if row["search_growth_7d"] > 0:
        return "strong 7-day search growth"
    return "stable recent search interest"


def demand_strength(row: pd.Series) -> str:
    if row["search_volume_score"] >= row["social_mentions_score"]:
        return "high search demand"
    return "strong recent social interest"


def urgency_strength(row: pd.Series) -> str:
    if row["days_until_peak"] <= 14:
        return "near-term peak demand"
    return "strong seasonal relevance"
