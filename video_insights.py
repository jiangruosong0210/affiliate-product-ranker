import pandas as pd


PRODUCT_MIN_VIDEOS = 5
PRODUCT_MIN_POSITIVE_VIEW_VIDEOS = 3
PRODUCT_MIN_CANDIDATE_OBSERVATIONS = 2
CATEGORY_MIN_VIDEOS = 10
CATEGORY_MIN_PRODUCTS = 3
CATEGORY_MIN_CANDIDATE_OBSERVATIONS = 3


def add_video_metrics(videos_df):
    result = videos_df.copy()
    result["engagement_rate"] = result.apply(calculate_engagement_rate, axis=1)
    result["like_rate"] = result.apply(
        lambda row: safe_rate(row["likes"], row["views"]),
        axis=1,
    )
    result["comment_rate"] = result.apply(
        lambda row: safe_rate(row["comments"], row["views"]),
        axis=1,
    )
    result["share_rate"] = result.apply(
        lambda row: safe_rate(row["shares"], row["views"]),
        axis=1,
    )
    result["view_to_follower_ratio"] = result.apply(
        lambda row: safe_rate(row["views"], row["creator_followers"]),
        axis=1,
    )
    result["duration_band"] = result["duration_seconds"].apply(duration_band)
    return result


def build_video_recommendations(videos_df, products_df):
    product_lookup = products_df.set_index("product_id")
    recommendations = []

    for product_id, product in product_lookup.iterrows():
        product_videos = videos_df[videos_df["product_id"] == product_id]
        category_videos = videos_df[
            videos_df["category"] == product["category"]
        ]

        if has_product_evidence(product_videos):
            evidence = product_videos
            evidence_level = "product-level evidence"
            minimum = PRODUCT_MIN_CANDIDATE_OBSERVATIONS
            fallback_explanation = ""
        elif has_category_evidence(category_videos):
            evidence = category_videos
            evidence_level = "category-level fallback"
            minimum = CATEGORY_MIN_CANDIDATE_OBSERVATIONS
            fallback_explanation = (
                "Product evidence was below threshold; category evidence was used."
            )
        else:
            recommendations.append(
                insufficient_recommendation(product_id, product, product_videos)
            )
            continue

        baseline = evidence["engagement_rate"].median(skipna=True)
        format_choice = best_group(
            evidence, "content_format", minimum, baseline
        )
        hook_choice = best_group(evidence, "hook_type", minimum, baseline)
        duration_choice = best_group(
            evidence, "duration_band", minimum, baseline
        )
        demo_choice = boolean_guidance(evidence, "demo_present", minimum)
        comparison_choice = boolean_guidance(
            evidence, "comparison_present", minimum
        )
        cta_choice = boolean_guidance(evidence, "cta_present", minimum)
        feature_choice = best_group(
            evidence[evidence["main_feature"] != ""],
            "main_feature",
            minimum,
            baseline,
        )

        valid_metric_count = int(evidence["engagement_rate"].notna().sum())
        recommendations.append(
            {
                "product_id": product_id,
                "product_name": product["product_name"],
                "category": product["category"],
                "evidence_level": evidence_level,
                "supporting_video_count": len(evidence),
                "valid_metric_count": valid_metric_count,
                "median_metric_used": baseline,
                "comparison_baseline": baseline,
                "preferred_content_format": format_choice["value"],
                "preferred_hook_type": hook_choice["value"],
                "suggested_duration_range": duration_choice["value"],
                "demo_guidance": demo_choice,
                "comparison_guidance": comparison_choice,
                "cta_guidance": cta_choice,
                "feature_to_emphasize": feature_choice["value"],
                "evidence_summary": evidence_summary(
                    evidence_level,
                    evidence,
                    valid_metric_count,
                    baseline,
                    format_choice,
                    fallback_explanation,
                ),
            }
        )

    return pd.DataFrame(recommendations)


def summarize_groups(videos_df, group_column):
    rows = []
    for value, group in videos_df.groupby(group_column, dropna=False):
        rows.append(
            {
                group_column: value,
                "video_count": len(group),
                "valid_engagement_count": int(
                    group["engagement_rate"].notna().sum()
                ),
                "median_views": group["views"].median(),
                "median_engagement_rate": group["engagement_rate"].median(
                    skipna=True
                ),
                "median_view_to_follower_ratio": group[
                    "view_to_follower_ratio"
                ].median(skipna=True),
            }
        )
    return pd.DataFrame(rows)


def calculate_engagement_rate(row):
    if row["views"] <= 0:
        return pd.NA
    components = [row["likes"], row["comments"], row["shares"]]
    if any(pd.isna(value) for value in components):
        return pd.NA
    return sum(components) / row["views"]


def safe_rate(numerator, denominator):
    if pd.isna(numerator) or pd.isna(denominator) or denominator <= 0:
        return pd.NA
    return numerator / denominator


def duration_band(seconds):
    if seconds < 15:
        return "under 15 seconds"
    if seconds < 30:
        return "15-29 seconds"
    if seconds < 60:
        return "30-59 seconds"
    if seconds < 120:
        return "60-119 seconds"
    return "120+ seconds"


def has_product_evidence(videos):
    return (
        len(videos) >= PRODUCT_MIN_VIDEOS
        and int((videos["views"] > 0).sum()) >= PRODUCT_MIN_POSITIVE_VIEW_VIDEOS
        and int(videos["engagement_rate"].notna().sum())
        >= PRODUCT_MIN_CANDIDATE_OBSERVATIONS
    )


def has_category_evidence(videos):
    return (
        len(videos) >= CATEGORY_MIN_VIDEOS
        and videos["product_id"].nunique() >= CATEGORY_MIN_PRODUCTS
        and int(videos["engagement_rate"].notna().sum())
        >= CATEGORY_MIN_CANDIDATE_OBSERVATIONS
    )


def best_group(videos, column, minimum, baseline):
    candidates = []
    for value, group in videos.groupby(column, dropna=False):
        metric_values = group["engagement_rate"].dropna()
        if len(metric_values) < minimum:
            continue
        candidates.append(
            {
                "value": value,
                "count": len(group),
                "valid_count": len(metric_values),
                "median": metric_values.median(),
                "view_ratio": group["view_to_follower_ratio"].median(
                    skipna=True
                ),
                "views": group["views"].median(),
            }
        )

    if not candidates:
        return {
            "value": "insufficient observations",
            "count": 0,
            "valid_count": 0,
            "median": pd.NA,
            "baseline": baseline,
        }

    candidates.sort(
        key=lambda item: (
            value_or_negative(item["median"]),
            value_or_negative(item["view_ratio"]),
            value_or_negative(item["views"]),
            item["valid_count"],
        ),
        reverse=True,
    )
    winner = candidates[0]
    winner["baseline"] = baseline
    return winner


def boolean_guidance(videos, column, minimum):
    known = videos[videos[column].isin([True, False])]
    true_metrics = known[known[column] == True]["engagement_rate"].dropna()  # noqa: E712
    false_metrics = known[known[column] == False]["engagement_rate"].dropna()  # noqa: E712
    if len(true_metrics) < minimum or len(false_metrics) < minimum:
        return "insufficient evidence"
    if true_metrics.median() > false_metrics.median():
        return "include"
    if true_metrics.median() < false_metrics.median():
        return "not supported by current evidence"
    return "no clear difference"


def insufficient_recommendation(product_id, product, videos):
    return {
        "product_id": product_id,
        "product_name": product["product_name"],
        "category": product["category"],
        "evidence_level": "insufficient evidence",
        "supporting_video_count": len(videos),
        "valid_metric_count": int(videos["engagement_rate"].notna().sum())
        if "engagement_rate" in videos
        else 0,
        "median_metric_used": pd.NA,
        "comparison_baseline": pd.NA,
        "preferred_content_format": "insufficient evidence",
        "preferred_hook_type": "insufficient evidence",
        "suggested_duration_range": "insufficient evidence",
        "demo_guidance": "insufficient evidence",
        "comparison_guidance": "insufficient evidence",
        "cta_guidance": "insufficient evidence",
        "feature_to_emphasize": "insufficient evidence",
        "evidence_summary": (
            f"Insufficient evidence: {len(videos)} valid product video(s). "
            "Product and category thresholds were not met."
        ),
    }


def evidence_summary(
    level,
    evidence,
    valid_metric_count,
    baseline,
    format_choice,
    fallback_explanation,
):
    baseline_text = (
        f"{baseline:.2%}" if not pd.isna(baseline) else "not available"
    )
    winner_text = (
        f"{format_choice['median']:.2%}"
        if not pd.isna(format_choice["median"])
        else "not available"
    )
    summary = (
        f"{level}: {len(evidence)} supporting videos, "
        f"{valid_metric_count} valid engagement observations. "
        f"Median engagement baseline {baseline_text}. "
        f"Preferred format '{format_choice['value']}' median {winner_text} "
        f"from {format_choice['valid_count']} valid observations."
    )
    if fallback_explanation:
        summary += f" {fallback_explanation}"
    return summary


def value_or_negative(value):
    return -1 if pd.isna(value) else float(value)
