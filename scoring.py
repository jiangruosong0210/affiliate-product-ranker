import pandas as pd


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


def normalize_series(values: pd.Series) -> pd.Series:
    minimum = values.min()
    maximum = values.max()

    if maximum == minimum:
        return pd.Series([50.0] * len(values), index=values.index)

    return ((values - minimum) / (maximum - minimum)) * 100


def score_products(products_df: pd.DataFrame) -> pd.DataFrame:
    ranked_df = products_df.copy()
    weights = SCORING_CONFIG["weights"]

    numeric_columns = [
        "price",
        "commission_rate",
        "trend_score",
        "demand_score",
        "competition_score",
        "urgency_score",
    ]
    for column in numeric_columns:
        ranked_df[column] = pd.to_numeric(ranked_df[column])

    ranked_df["commission_potential"] = (
        ranked_df["price"] * ranked_df["commission_rate"]
    )
    ranked_df["normalized_commission"] = normalize_series(
        ranked_df["commission_potential"]
    )
    ranked_df["competition_opportunity"] = 100 - ranked_df["competition_score"]

    ranked_df["commission_contribution"] = (
        ranked_df["normalized_commission"] * weights["commission"]
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
    ranked_df["profit_potential_score"] = ranked_df["profit_potential_score"].round(2)
    ranked_df["commission_potential"] = ranked_df["commission_potential"].round(2)
    ranked_df["normalized_commission"] = ranked_df["normalized_commission"].round(2)
    ranked_df["competition_opportunity"] = ranked_df[
        "competition_opportunity"
    ].round(2)

    for column in contribution_columns:
        ranked_df[column] = ranked_df[column].round(2)

    ranked_df["explanation"] = ranked_df.apply(generate_explanation, axis=1)
    ranked_df = ranked_df.sort_values(
        by="profit_potential_score", ascending=False
    ).reset_index(drop=True)
    ranked_df.insert(0, "rank", ranked_df.index + 1)

    return ranked_df


def generate_explanation(row: pd.Series) -> str:
    factors = [
        ("commission_contribution", "good commission opportunity"),
        ("trend_contribution", "strong trend"),
        ("demand_contribution", "strong buyer demand"),
        ("competition_contribution", "lower competition"),
        ("urgency_contribution", "short-term urgency"),
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
    risk = weakness if weakness else "no major weakness stands out in this CSV"
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
    if row["normalized_commission"] <= 35:
        weaknesses.append(
            ("low commission opportunity in this CSV", row["commission_contribution"])
        )

    if not weaknesses:
        return ""

    return min(weaknesses, key=lambda item: item[1])[0]


def recommend_action(row: pd.Series, weakness: str) -> str:
    score = row["profit_potential_score"]

    if score >= 70 and not weakness:
        return "Prioritize this product for a short-term campaign test"
    if score >= 60:
        return "Test with a small campaign before scaling"
    if score >= 45:
        return "Keep as a backup option and compare against stronger products"
    return "Do not prioritize yet unless you have a specific audience fit"
