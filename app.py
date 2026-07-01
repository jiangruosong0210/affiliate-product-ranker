import html
from copy import deepcopy
from pathlib import Path
from time import perf_counter

import pandas as pd
import streamlit as st

from creative_planning import (
    ALLOWED_DURATIONS,
    CAMPAIGN_OBJECTIVES,
    CONTENT_TEMPLATES,
    DEFAULT_DISCLOSURE,
    PLATFORM_PRESETS,
    brief_csv_bytes,
    dataframe_csv_bytes,
    json_bytes,
    package_zip_bytes,
    text_bytes,
    validate_creative_package,
    build_creative_package,
)
from data_quality import validate_offer_records, validate_product_records
from market_data.manual_provider import ManualProvider
from market_data.mock_provider import MockProvider
from market_data.service import process_market_data
from offer_scoring import OFFER_SCORING_CONFIG, score_offers
from scoring import SCORING_CONFIG, score_products
from video_generation_provider import (
    ACTIVE_VIDEO_STATUSES,
    VIDEO_STATUS_COMPLETED,
    dataclass_to_dict,
)
from video_generation_service import (
    build_video_generation_request,
    cancel_video_generation,
    get_video_provider_registry,
    refresh_video_generation,
    safe_filename,
    submit_video_generation,
)
from video_insights import (
    add_video_metrics,
    build_video_recommendations,
    summarize_groups,
)
from video_text_analysis import (
    apply_label_precedence,
    enrich_video_text,
)
from video_upload_processing import process_uploaded_video
from video_validation import validate_video_records


PROJECT_DIR = Path(__file__).resolve().parent
PRODUCT_TEMPLATE_PATH = PROJECT_DIR / "sample_products.csv"
OFFER_TEMPLATE_PATH = PROJECT_DIR / "sample_offers.csv"
VIDEO_TEMPLATE_PATH = PROJECT_DIR / "sample_videos.csv"


@st.cache_resource
def get_provider_registry():
    return {
        "Manual CSV": ManualProvider(),
        "Mock automatic data": MockProvider(),
    }


def read_uploaded_csv(uploaded_file):
    if uploaded_file is None:
        return None, ""
    try:
        return pd.read_csv(uploaded_file), ""
    except Exception as exc:
        return None, f"Could not read {uploaded_file.name}: {exc}"


def show_top_three(top_three_df):
    columns = st.columns(3)
    for index, column in enumerate(columns):
        if index >= len(top_three_df):
            column.empty()
            continue
        product = top_three_df.iloc[index]
        column.metric(
            f"#{int(product['rank'])} {product['product_name']}",
            f"{product['profit_potential_score']:.2f}",
            f"${product['commission_per_sale']:.2f} reference commission",
        )
        column.caption(product["category"])


def show_score_bar_chart(dataframe, score_column):
    if dataframe.empty:
        return
    maximum = max(dataframe[score_column].max(), 1)
    chart_html = ""
    for _, row in dataframe.iterrows():
        label = html.escape(str(row["product_name"]))
        score = row[score_column]
        chart_html += f"""
        <div style="margin-bottom: 0.75rem;">
            <div style="display:flex;justify-content:space-between;gap:1rem;">
                <span>{label}</span><strong>{score:.2f}</strong>
            </div>
            <div style="background:#eee;height:0.75rem;border-radius:0.25rem;">
                <div style="background:#4f8bf9;width:{score / maximum * 100:.2f}%;
                    height:0.75rem;border-radius:0.25rem;"></div>
            </div>
        </div>
        """
    st.markdown(chart_html, unsafe_allow_html=True)


def summarize_filtered_features(dataframe):
    counts = {}
    if dataframe.empty or "detected_main_features" not in dataframe:
        return pd.DataFrame(columns=["feature", "video_count"])
    for value in dataframe["detected_main_features"]:
        if pd.isna(value) or not str(value).strip():
            continue
        for feature in str(value).split(";"):
            feature = feature.strip()
            if feature:
                counts[feature] = counts.get(feature, 0) + 1
    rows = [
        {"feature": feature, "video_count": count}
        for feature, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    return pd.DataFrame(rows)


def summarize_agreement(comparison_df):
    rows = []
    for column in [
        "content_format_agreement",
        "hook_type_agreement",
        "cta_present_agreement",
        "main_feature_agreement",
    ]:
        if column not in comparison_df:
            continue
        counts = comparison_df[column].value_counts(dropna=False)
        for status, count in counts.items():
            rows.append(
                {
                    "field": column.replace("_agreement", ""),
                    "agreement_status": status,
                    "video_count": int(count),
                }
            )
    return pd.DataFrame(rows)


def reset_creative_state():
    for key in [
        "creative_baseline_package",
        "creative_baseline_script",
        "creative_baseline_storyboard",
        "creative_edited_script",
        "creative_dirty",
        "creative_last_settings",
    ]:
        st.session_state.pop(key, None)


def reset_video_generation_state():
    for key in [
        "video_generation_request",
        "video_generation_signature",
        "video_generation_job",
        "video_generation_result",
        "video_generation_error",
    ]:
        st.session_state.pop(key, None)


def selected_recommended_offer(scored_offers_df, product_id):
    if scored_offers_df.empty:
        return None
    eligible = scored_offers_df[
        (scored_offers_df["product_id"] == product_id)
        & (scored_offers_df["recommended_offer"])
    ]
    if eligible.empty:
        return None
    return eligible.iloc[0].to_dict()


def selected_video_recommendation(video_recommendations_df, product_id):
    if video_recommendations_df.empty:
        return None
    matches = video_recommendations_df[
        video_recommendations_df["product_id"] == product_id
    ]
    if matches.empty:
        return None
    return matches.iloc[0].to_dict()


def edited_creative_package(storyboard_df, script_text):
    package = deepcopy(st.session_state.creative_baseline_package)
    package["script_text"] = script_text
    package["storyboard"] = storyboard_df.to_dict("records")
    package["provider_neutral_payload"]["scenes"] = package["storyboard"]
    package["validation_warnings"] = validate_creative_package(package)
    return package


st.set_page_config(page_title="Affiliate Product Ranker", layout="wide")
st.title("Affiliate Product Ranker")
st.write(
    "Compare product market opportunity and platform-specific affiliate offers "
    "for the next 7-30 days."
)
st.info(
    "Version 1.9 keeps the existing ranking, offer, video-insight, and "
    "Creative Studio logic, then adds a mock-first Video Generator workflow "
    "for testing provider-neutral generation jobs without external API calls."
)
st.warning(
    "This application provides estimated scores for demonstration and "
    "decision-support purposes only. It does not guarantee affiliate revenue "
    "or profit. Synthetic files and mock-provider values are not real market data."
)

mode = st.radio(
    "Product market-data mode",
    ["Manual CSV", "Mock automatic data"],
    horizontal=True,
)
validation_mode = "manual" if mode == "Manual CSV" else "automatic"
if mode == "Mock automatic data":
    st.warning(
        "Mock automatic data is deterministic synthetic test data, not observed "
        "market data."
    )

upload_columns = st.columns(3)
with upload_columns[0]:
    products_file = st.file_uploader("Upload products.csv", type=["csv"])
    st.download_button(
        "Download products CSV template",
        PRODUCT_TEMPLATE_PATH.read_bytes(),
        file_name="sample_products.csv",
        mime="text/csv",
    )
with upload_columns[1]:
    offers_file = st.file_uploader("Upload offers.csv (optional)", type=["csv"])
    st.download_button(
        "Download offers CSV template",
        OFFER_TEMPLATE_PATH.read_bytes(),
        file_name="sample_offers.csv",
        mime="text/csv",
    )
with upload_columns[2]:
    videos_file = st.file_uploader("Upload videos.csv (optional)", type=["csv"])
    st.download_button(
        "Download video CSV template",
        VIDEO_TEMPLATE_PATH.read_bytes(),
        file_name="sample_videos.csv",
        mime="text/csv",
    )

products_input, product_read_error = read_uploaded_csv(products_file)
offers_input, offer_read_error = read_uploaded_csv(offers_file)
videos_input, video_read_error = read_uploaded_csv(videos_file)

for read_error in [product_read_error, offer_read_error, video_read_error]:
    if read_error:
        st.error(read_error)

valid_products = pd.DataFrame()
excluded_products = pd.DataFrame()
signal_df = pd.DataFrame()
failed_provider_df = pd.DataFrame()
ranked_products = pd.DataFrame()
valid_offers = pd.DataFrame()
excluded_offers = pd.DataFrame()
scored_offers = pd.DataFrame()
valid_videos = pd.DataFrame()
excluded_videos = pd.DataFrame()
video_warnings = pd.DataFrame()
video_text_warnings = pd.DataFrame()
video_label_comparison = pd.DataFrame()
video_feature_summary = pd.DataFrame()
video_metrics = pd.DataFrame()
video_recommendations = pd.DataFrame()
timings = {
    "product_validation": 0.0,
    "provider_processing": 0.0,
    "product_scoring": 0.0,
    "offer_validation": 0.0,
    "offer_scoring": 0.0,
    "video_validation": 0.0,
    "video_analysis": 0.0,
    "total": 0.0,
}

processing_started = perf_counter()
if products_input is not None:
    started = perf_counter()
    valid_products, excluded_products = validate_product_records(
        products_input,
        mode=validation_mode,
    )
    timings["product_validation"] = perf_counter() - started

    if not valid_products.empty:
        providers = get_provider_registry()
        if "provider_result_cache" not in st.session_state:
            st.session_state.provider_result_cache = {}
        cache = (
            st.session_state.provider_result_cache
            if mode == "Mock automatic data"
            else {}
        )

        started = perf_counter()
        signal_df, failed_provider_df = process_market_data(
            valid_products,
            providers[mode],
            result_cache=cache,
        )
        timings["provider_processing"] = perf_counter() - started

        if not signal_df.empty:
            started = perf_counter()
            ranked_products = score_products(signal_df)
            timings["product_scoring"] = perf_counter() - started

    if offers_input is not None and not valid_products.empty:
        started = perf_counter()
        valid_product_ids = set(valid_products["product_id"])
        valid_offers, excluded_offers = validate_offer_records(
            offers_input,
            valid_product_ids,
        )
        timings["offer_validation"] = perf_counter() - started

        if not valid_offers.empty:
            started = perf_counter()
            scored_offers = score_offers(valid_offers)
            product_names = valid_products[["product_id", "product_name"]]
            scored_offers = scored_offers.merge(
                product_names,
                on="product_id",
                how="left",
            )
            timings["offer_scoring"] = perf_counter() - started

    if videos_input is not None and not valid_products.empty:
        started = perf_counter()
        valid_videos, excluded_videos, video_warnings = validate_video_records(
            videos_input,
            set(valid_products["product_id"]),
        )
        timings["video_validation"] = perf_counter() - started

        if not valid_videos.empty:
            started = perf_counter()
            product_context = valid_products[
                ["product_id", "product_name", "category"]
            ]
            video_metrics = add_video_metrics(valid_videos).merge(
                product_context,
                on="product_id",
                how="left",
            )
            (
                video_metrics,
                video_text_warnings,
                video_label_comparison,
                video_feature_summary,
            ) = enrich_video_text(video_metrics)
            recommendation_input = apply_label_precedence(
                video_metrics,
                "Manual first, detected fallback",
            )
            video_recommendations = build_video_recommendations(
                recommendation_input,
                valid_products,
            )
            timings["video_analysis"] = perf_counter() - started

timings["total"] = perf_counter() - processing_started

tabs = st.tabs(
    [
        "Overview",
        "Product Ranking",
        "Platform Offer Comparison",
        "Video Insights",
        "Creative Studio",
        "Video Generator",
        "Data Quality",
        "Scalability",
        "Methodology",
    ]
)

with tabs[0]:
    if products_input is None:
        st.write("Upload a products CSV to begin.")
    else:
        provider_status = (
            pd.concat([signal_df, failed_provider_df], ignore_index=True)
            if not signal_df.empty or not failed_provider_df.empty
            else pd.DataFrame()
        )
        success_count = (
            int((provider_status["retrieval_status"] == "success").sum())
            if not provider_status.empty
            else 0
        )
        fallback_count = (
            int((provider_status["retrieval_status"] == "fallback").sum())
            if not provider_status.empty
            else 0
        )
        failed_count = (
            int((provider_status["retrieval_status"] == "failed").sum())
            if not provider_status.empty
            else 0
        )
        overview_metrics = st.columns(6)
        overview_metrics[0].metric("Valid products", len(valid_products))
        overview_metrics[1].metric("Valid offers", len(valid_offers))
        overview_metrics[2].metric(
            "Platforms",
            valid_offers["platform"].nunique() if not valid_offers.empty else 0,
        )
        overview_metrics[3].metric(
            "Average offers/product",
            (
                f"{len(valid_offers) / len(valid_products):.2f}"
                if len(valid_products)
                else "0.00"
            ),
        )
        overview_metrics[4].metric("Valid videos", len(valid_videos))
        overview_metrics[5].metric(
            "Excluded records",
            len(excluded_products)
            + len(excluded_offers)
            + len(excluded_videos)
            + len(failed_provider_df),
        )

        status_metrics = st.columns(4)
        status_metrics[0].metric("Provider success", success_count)
        status_metrics[1].metric("Fallback", fallback_count)
        status_metrics[2].metric("Failed", failed_count)
        status_metrics[3].metric("Processing time", f"{timings['total']:.3f}s")

        if not ranked_products.empty:
            top_product = ranked_products.iloc[0]
            st.subheader("Top Product")
            st.metric(
                top_product["product_name"],
                f"{top_product['profit_potential_score']:.2f}",
                "Product Opportunity Score",
            )
            if not scored_offers.empty:
                recommended = scored_offers[
                    (scored_offers["product_id"] == top_product["product_id"])
                    & scored_offers["recommended_offer"]
                ]
                if not recommended.empty:
                    offer = recommended.iloc[0]
                    st.write(
                        f"Recommended offer: **{offer['platform']}** "
                        f"({offer['payout_type']}, score "
                        f"{offer['platform_offer_score']:.2f})"
                    )
                else:
                    st.write("No eligible active or unknown offer is available.")

with tabs[1]:
    st.subheader("Product Opportunity Ranking")
    st.caption(
        "Reference price and commission rate preserve the existing product-level "
        "score. They are separate from platform offer economics."
    )
    if ranked_products.empty:
        st.write("Upload valid product data to view rankings.")
    else:
        filtered_products = ranked_products.copy()
        filter_columns = st.columns(2)
        selected_categories = filter_columns[0].multiselect(
            "Product category",
            sorted(filtered_products["category"].unique()),
            default=sorted(filtered_products["category"].unique()),
        )
        filtered_products = filtered_products[
            filtered_products["category"].isin(selected_categories)
        ]

        if not scored_offers.empty:
            platforms = sorted(scored_offers["platform"].unique())
            selected_platforms = filter_columns[1].multiselect(
                "Linked offer platform",
                platforms,
                default=platforms,
            )
            linked_ids = set(
                scored_offers[
                    scored_offers["platform"].isin(selected_platforms)
                ]["product_id"]
            )
            filtered_products = filtered_products[
                filtered_products["product_id"].isin(linked_ids)
            ]

        if filtered_products.empty:
            st.warning("No products match the selected filters.")
        else:
            top_n = st.number_input(
                "Top N products",
                min_value=1,
                max_value=len(filtered_products),
                value=min(10, len(filtered_products)),
                step=1,
            )
            top_products = filtered_products.head(top_n)
            show_top_three(top_products.head(3))
            st.subheader("Product Score Chart")
            show_score_bar_chart(top_products, "profit_potential_score")
            st.dataframe(top_products, width="stretch")
            st.download_button(
                "Download ranked products",
                top_products.to_csv(index=False).encode("utf-8"),
                file_name="ranked_products.csv",
                mime="text/csv",
            )

with tabs[2]:
    st.subheader("Platform Offer Comparison")
    if offers_input is None:
        st.write("Upload an offers CSV to activate platform comparison.")
    elif scored_offers.empty:
        st.warning("No valid offers are available for comparison.")
    else:
        filters = st.columns(5)
        product_options = sorted(scored_offers["product_name"].unique())
        platform_options = sorted(scored_offers["platform"].unique())
        payout_options = sorted(scored_offers["payout_type"].unique())
        status_options = sorted(scored_offers["offer_status"].unique())
        selected_products = filters[0].multiselect(
            "Product",
            product_options,
            default=product_options,
        )
        selected_offer_platforms = filters[1].multiselect(
            "Platform",
            platform_options,
            default=platform_options,
        )
        selected_payouts = filters[2].multiselect(
            "Payout type",
            payout_options,
            default=payout_options,
        )
        selected_recurring = filters[3].multiselect(
            "Recurring",
            [True, False],
            default=[True, False],
        )
        selected_statuses = filters[4].multiselect(
            "Offer status",
            status_options,
            default=status_options,
        )
        filtered_offers = scored_offers[
            scored_offers["product_name"].isin(selected_products)
            & scored_offers["platform"].isin(selected_offer_platforms)
            & scored_offers["payout_type"].isin(selected_payouts)
            & scored_offers["recurring_commission"].isin(selected_recurring)
            & scored_offers["offer_status"].isin(selected_statuses)
        ]
        display_columns = [
            "product_name",
            "platform",
            "payout_type",
            "offer_price",
            "commission_rate",
            "commission_value",
            "cookie_duration_days",
            "recurring_commission",
            "offer_status",
            "platform_offer_score",
            "commission_value_contribution",
            "commission_rate_contribution",
            "cookie_duration_contribution",
            "recurring_contribution",
            "status_contribution",
            "strengths",
            "risks",
            "recommended_action",
            "affiliate_url",
            "recommended_offer",
            "recommendation_warning",
        ]
        st.dataframe(filtered_offers[display_columns], width="stretch")
        st.download_button(
            "Download offer comparison",
            filtered_offers.to_csv(index=False).encode("utf-8"),
            file_name="platform_offer_comparison.csv",
            mime="text/csv",
        )

        st.subheader("Compare One Product")
        comparison_product = st.selectbox("Selected product", product_options)
        comparison = scored_offers[
            scored_offers["product_name"] == comparison_product
        ]
        st.dataframe(comparison[display_columns], width="stretch")

with tabs[3]:
    st.subheader("Video Insights")
    st.caption(
        "Video insights summarize structured performance evidence. They do not "
        "estimate revenue, conversion, or profitability."
    )
    st.subheader("Uploaded Video Processing")
    st.caption(
        "Version 1.7 inspects one uploaded MP4 at a time using local, "
        "lightweight metadata and frame heuristics."
    )
    upload_video_columns = st.columns(2)
    with upload_video_columns[0]:
        uploaded_mp4 = st.file_uploader(
            "Upload one MP4 video",
            type=["mp4"],
            key="uploaded_mp4_video",
        )
        transcript_file = st.file_uploader(
            "Upload transcript.txt (optional)",
            type=["txt"],
            key="uploaded_video_transcript",
        )
    with upload_video_columns[1]:
        associated_product = None
        if not valid_products.empty:
            product_options = ["Unassigned"] + [
                f"{row['product_id']} - {row['product_name']}"
                for _, row in valid_products.iterrows()
            ]
            selected_product_label = st.selectbox(
                "Associated product",
                product_options,
            )
            if selected_product_label != "Unassigned":
                selected_product_id = selected_product_label.split(" - ", 1)[0]
                product_row = valid_products[
                    valid_products["product_id"] == selected_product_id
                ].iloc[0]
                associated_product = {
                    "product_id": product_row["product_id"],
                    "product_name": product_row["product_name"],
                    "category": product_row["category"],
                }
        else:
            st.info("Upload valid product data to associate the video with a product.")

        uploaded_video_title = st.text_input("Video title (optional)")
        uploaded_video_description = st.text_area(
            "Video description (optional)",
            height=90,
        )
        uploaded_video_hashtags = st.text_input("Video hashtags (optional)")
        uploaded_video_language = st.text_input("Video language (optional)")
    transcript_text = st.text_area(
        "Paste transcript text (optional)",
        height=120,
    )
    process_uploaded_button = st.button(
        "Process uploaded MP4",
        disabled=uploaded_mp4 is None,
    )

    if uploaded_mp4 is not None:
        st.video(uploaded_mp4.getvalue())

    if process_uploaded_button and uploaded_mp4 is not None:
        uploaded_transcript = transcript_text
        if transcript_file is not None:
            try:
                transcript_from_file = transcript_file.getvalue().decode("utf-8")
                uploaded_transcript = "\n".join(
                    part for part in [uploaded_transcript, transcript_from_file]
                    if part.strip()
                )
            except UnicodeDecodeError:
                st.warning("Transcript file could not be decoded as UTF-8.")

        with st.spinner("Processing uploaded MP4..."):
            upload_result = process_uploaded_video(
                uploaded_mp4,
                associated_product=associated_product,
                title=uploaded_video_title,
                description=uploaded_video_description,
                transcript=uploaded_transcript,
                hashtags=uploaded_video_hashtags,
                language=uploaded_video_language,
            )
            uploaded_text_analysis, upload_text_warnings, upload_comparison, upload_features = (
                enrich_video_text(upload_result["text_record"])
            )
            effective_upload_text = apply_label_precedence(
                uploaded_text_analysis,
                "Manual first, detected fallback",
            )

        metadata_df = pd.DataFrame([upload_result["metadata"]])
        visual_df = pd.DataFrame([upload_result["visual_features"]])
        association_df = pd.DataFrame([upload_result["association"]])
        report_df = upload_result["report"]

        status = upload_result["metadata"]["processing_status"]
        if status == "success":
            st.success("Uploaded video processed successfully.")
        elif status == "partial":
            st.warning("Uploaded video was partially processed.")
        elif status == "rejected":
            st.error("Uploaded video was rejected.")
        else:
            st.error("Uploaded video processing failed.")

        if upload_result["errors"]:
            st.error("; ".join(upload_result["errors"]))
        if upload_result["warnings"]:
            st.warning("; ".join(upload_result["warnings"]))

        st.write("Metadata Summary")
        st.dataframe(metadata_df, width="stretch")
        st.write("Product Association")
        st.dataframe(association_df, width="stretch")
        st.write("Approximate Visual Heuristics")
        st.caption(
            "These are lightweight heuristics from sampled frames, not semantic "
            "video understanding."
        )
        st.dataframe(visual_df, width="stretch")

        if upload_result["contact_sheet_bytes"]:
            st.write("Sampled Frame Contact Sheet")
            st.image(upload_result["contact_sheet_bytes"])

        st.write("Transcript-Based Version 1.6 Analysis")
        st.dataframe(effective_upload_text, width="stretch")
        if not upload_comparison.empty:
            st.write("Uploaded Video Manual vs Detected Comparison")
            st.dataframe(upload_comparison, width="stretch")
        if not upload_text_warnings.empty:
            st.write("Uploaded Video Text Warnings")
            st.dataframe(upload_text_warnings, width="stretch")
        if not upload_features.empty:
            st.write("Uploaded Video Extracted Features")
            st.dataframe(upload_features, width="stretch")

        uploaded_downloads = st.columns(5)
        uploaded_downloads[0].download_button(
            "Download video metadata",
            metadata_df.to_csv(index=False).encode("utf-8"),
            file_name="video_metadata.csv",
            mime="text/csv",
        )
        uploaded_downloads[1].download_button(
            "Download sampled frames ZIP",
            upload_result["sampled_frames_zip_bytes"],
            file_name="sampled_frames.zip",
            mime="application/zip",
            disabled=not bool(upload_result["sampled_frames_zip_bytes"]),
        )
        uploaded_downloads[2].download_button(
            "Download contact sheet",
            upload_result["contact_sheet_bytes"],
            file_name="contact_sheet.png",
            mime="image/png",
            disabled=not bool(upload_result["contact_sheet_bytes"]),
        )
        uploaded_downloads[3].download_button(
            "Download video processing report",
            report_df.to_csv(index=False).encode("utf-8"),
            file_name="video_processing_report.csv",
            mime="text/csv",
        )
        uploaded_downloads[4].download_button(
            "Download uploaded video text analysis",
            effective_upload_text.to_csv(index=False).encode("utf-8"),
            file_name="uploaded_video_text_analysis.csv",
            mime="text/csv",
        )

    if videos_input is None:
        st.write(
            "Upload an optional videos CSV to analyze promotional video patterns."
        )
    elif video_metrics.empty:
        st.warning("No valid video rows are available for analysis.")
        if not excluded_videos.empty:
            st.download_button(
                "Download video exclusion report",
                excluded_videos.to_csv(index=False).encode("utf-8"),
                file_name="excluded_videos.csv",
                mime="text/csv",
            )
    else:
        label_mode = st.selectbox(
            "Label mode",
            [
                "Manual first, detected fallback",
                "Manual labels only",
                "Detected labels only",
                "Compare only",
            ],
        )
        recommendation_videos = apply_label_precedence(video_metrics, label_mode)
        displayed_recommendations = build_video_recommendations(
            recommendation_videos,
            valid_products,
        )

        first_filters = st.columns(5)
        product_values = sorted(video_metrics["product_name"].unique())
        category_values = sorted(video_metrics["category"].unique())
        platform_values = sorted(video_metrics["platform"].unique())
        format_values = sorted(video_metrics["content_format"].unique())
        hook_values = sorted(video_metrics["hook_type"].unique())
        selected_video_products = first_filters[0].multiselect(
            "Video product",
            product_values,
            default=product_values,
        )
        selected_video_categories = first_filters[1].multiselect(
            "Video category",
            category_values,
            default=category_values,
        )
        selected_video_platforms = first_filters[2].multiselect(
            "Video platform",
            platform_values,
            default=platform_values,
        )
        selected_formats = first_filters[3].multiselect(
            "Content format",
            format_values,
            default=format_values,
        )
        selected_hooks = first_filters[4].multiselect(
            "Hook type",
            hook_values,
            default=hook_values,
        )

        second_filters = st.columns(5)
        duration_values = [
            "under 15 seconds",
            "15-29 seconds",
            "30-59 seconds",
            "60-119 seconds",
            "120+ seconds",
        ]
        selected_durations = second_filters[0].multiselect(
            "Duration range",
            duration_values,
            default=duration_values,
        )
        selected_demo = second_filters[1].multiselect(
            "Demo present",
            [True, False],
            default=[True, False],
        )
        selected_comparison = second_filters[2].multiselect(
            "Comparison present",
            [True, False],
            default=[True, False],
        )
        selected_cta = second_filters[3].multiselect(
            "CTA present",
            [True, False],
            default=[True, False],
        )
        feature_values = sorted(
            value for value in video_metrics["main_feature"].unique() if value
        )
        selected_features = second_filters[4].multiselect(
            "Main feature",
            feature_values,
            default=feature_values,
        )

        text_filters = st.columns(4)
        language_values = sorted(video_metrics["normalized_language"].unique())
        detected_format_values = sorted(
            video_metrics["detected_content_format"].unique()
        )
        detected_hook_values = sorted(video_metrics["detected_hook_type"].unique())
        text_status_values = sorted(video_metrics["text_analysis_status"].unique())
        selected_languages = text_filters[0].multiselect(
            "Language",
            language_values,
            default=language_values,
        )
        selected_detected_formats = text_filters[1].multiselect(
            "Detected format",
            detected_format_values,
            default=detected_format_values,
        )
        selected_detected_hooks = text_filters[2].multiselect(
            "Detected hook",
            detected_hook_values,
            default=detected_hook_values,
        )
        selected_text_statuses = text_filters[3].multiselect(
            "Text analysis status",
            text_status_values,
            default=text_status_values,
        )

        detected_cta_values = [
            value
            for value in [True, False]
            if value in set(video_metrics["detected_cta_present"].dropna())
        ]
        if detected_cta_values:
            selected_detected_cta = st.multiselect(
                "Detected CTA present",
                detected_cta_values,
                default=detected_cta_values,
            )
        else:
            selected_detected_cta = []

        filtered_videos = video_metrics[
            video_metrics["product_name"].isin(selected_video_products)
            & video_metrics["category"].isin(selected_video_categories)
            & video_metrics["platform"].isin(selected_video_platforms)
            & video_metrics["content_format"].isin(selected_formats)
            & video_metrics["hook_type"].isin(selected_hooks)
            & video_metrics["duration_band"].isin(selected_durations)
            & video_metrics["normalized_language"].isin(selected_languages)
            & video_metrics["detected_content_format"].isin(
                selected_detected_formats
            )
            & video_metrics["detected_hook_type"].isin(selected_detected_hooks)
            & video_metrics["text_analysis_status"].isin(selected_text_statuses)
        ]
        if selected_detected_cta:
            filtered_videos = filtered_videos[
                filtered_videos["detected_cta_present"].isna()
                | filtered_videos["detected_cta_present"].isin(
                    selected_detected_cta
                )
            ]
        if selected_features:
            filtered_videos = filtered_videos[
                filtered_videos["main_feature"].isin(selected_features)
            ]
        filtered_videos = filtered_videos[
            (
                filtered_videos["demo_present"].isna()
                | filtered_videos["demo_present"].isin(selected_demo)
            )
            & (
                filtered_videos["comparison_present"].isna()
                | filtered_videos["comparison_present"].isin(
                    selected_comparison
                )
            )
            & (
                filtered_videos["cta_present"].isna()
                | filtered_videos["cta_present"].isin(selected_cta)
            )
        ]

        metric_columns = st.columns(4)
        metric_columns[0].metric("Videos", len(filtered_videos))
        metric_columns[1].metric(
            "Median views",
            (
                f"{filtered_videos['views'].median():,.0f}"
                if not filtered_videos.empty
                else "0"
            ),
        )
        median_engagement = filtered_videos["engagement_rate"].median(
            skipna=True
        )
        metric_columns[2].metric(
            "Median engagement",
            (
                f"{median_engagement:.2%}"
                if not pd.isna(median_engagement)
                else "Unavailable"
            ),
        )
        metric_columns[3].metric(
            "Valid engagement observations",
            int(filtered_videos["engagement_rate"].notna().sum()),
        )

        st.subheader("Text Coverage")
        coverage_columns = st.columns(5)
        coverage_columns[0].metric(
            "With description",
            int((filtered_videos["description"].astype(str).str.strip() != "").sum()),
        )
        coverage_columns[1].metric(
            "With transcript",
            int((filtered_videos["transcript"].astype(str).str.strip() != "").sum()),
        )
        coverage_columns[2].metric(
            "With hashtags",
            int((filtered_videos["hashtags"].astype(str).str.strip() != "").sum()),
        )
        coverage_columns[3].metric(
            "Analyzed text",
            int((filtered_videos["text_analysis_status"] == "analyzed").sum()),
        )
        coverage_columns[4].metric(
            "Text warnings",
            len(video_text_warnings),
        )

        st.subheader("Automated Content Detection")
        detection_columns = [
            "video_id",
            "product_name",
            "detected_content_format",
            "detected_content_format_evidence",
            "detected_content_format_confidence",
            "detected_hook_type",
            "detected_hook_phrase",
            "detected_hook_confidence",
            "detected_cta_present",
            "detected_cta_phrase",
            "detected_cta_type",
            "text_analysis_status",
            "text_analysis_notes",
        ]
        st.dataframe(filtered_videos[detection_columns], width="stretch")

        st.subheader("Top Extracted Features")
        filtered_features = summarize_filtered_features(filtered_videos)
        st.dataframe(filtered_features, width="stretch")
        if not filtered_features.empty:
            st.bar_chart(
                filtered_features.set_index("feature")[["video_count"]]
            )

        st.subheader("Manual vs Detected Comparison")
        st.caption("Agreement is a consistency check, not an accuracy claim.")
        filtered_comparison = video_label_comparison[
            video_label_comparison["video_id"].isin(filtered_videos["video_id"])
        ]
        agreement_summary = summarize_agreement(filtered_comparison)
        st.dataframe(agreement_summary, width="stretch")
        st.dataframe(filtered_comparison, width="stretch")

        st.subheader("Insufficient Text Warnings")
        if video_text_warnings.empty:
            st.success("No text-analysis warnings were generated.")
        else:
            st.dataframe(video_text_warnings, width="stretch")

        st.subheader("Cleaned Video Data")
        st.dataframe(filtered_videos, width="stretch")
        summary_choice = st.selectbox(
            "Summarize by",
            [
                "platform",
                "content_format",
                "hook_type",
                "duration_band",
                "demo_present",
                "comparison_present",
                "cta_present",
                "main_feature",
            ],
        )
        summary = summarize_groups(filtered_videos, summary_choice)
        st.subheader("Performance Summary")
        st.dataframe(summary, width="stretch")
        if not summary.empty:
            chart_data = summary.dropna(
                subset=["median_engagement_rate"]
            ).set_index(summary_choice)[["median_engagement_rate"]]
            st.bar_chart(chart_data)

        st.subheader("Product-Level Promotion Recommendations")
        st.dataframe(displayed_recommendations, width="stretch")

        video_downloads = st.columns(4)
        video_downloads[0].download_button(
            "Download cleaned videos",
            video_metrics.to_csv(index=False).encode("utf-8"),
            file_name="cleaned_videos.csv",
            mime="text/csv",
        )
        video_downloads[1].download_button(
            "Download video exclusions",
            excluded_videos.to_csv(index=False).encode("utf-8"),
            file_name="excluded_videos.csv",
            mime="text/csv",
        )
        video_downloads[2].download_button(
            "Download video warnings",
            video_warnings.to_csv(index=False).encode("utf-8"),
            file_name="video_warnings.csv",
            mime="text/csv",
        )
        video_downloads[3].download_button(
            "Download video recommendations",
            displayed_recommendations.to_csv(index=False).encode("utf-8"),
            file_name="video_recommendations.csv",
            mime="text/csv",
        )
        text_downloads = st.columns(4)
        text_downloads[0].download_button(
            "Download enriched videos",
            video_metrics.to_csv(index=False).encode("utf-8"),
            file_name="enriched_videos.csv",
            mime="text/csv",
        )
        text_downloads[1].download_button(
            "Download video text warnings",
            video_text_warnings.to_csv(index=False).encode("utf-8"),
            file_name="video_text_warnings.csv",
            mime="text/csv",
        )
        text_downloads[2].download_button(
            "Download manual detected comparison",
            video_label_comparison.to_csv(index=False).encode("utf-8"),
            file_name="manual_detected_comparison.csv",
            mime="text/csv",
        )
        text_downloads[3].download_button(
            "Download extracted feature summary",
            video_feature_summary.to_csv(index=False).encode("utf-8"),
            file_name="extracted_feature_summary.csv",
            mime="text/csv",
        )

with tabs[4]:
    st.subheader("Creative Studio")
    st.caption(
        "Create a provider-neutral short-form video plan from uploaded product, "
        "offer, and video-insight data. This does not generate video, audio, "
        "images, revenue predictions, or automatic posts."
    )
    st.info(
        "Creative outputs are deterministic planning drafts. Mock data and "
        "synthetic recommendations must not be presented as real market evidence."
    )

    if ranked_products.empty:
        st.write("Upload valid product data to create a video brief.")
    else:
        product_labels = [
            f"{row['product_id']} - {row['product_name']}"
            for _, row in ranked_products.iterrows()
        ]
        selected_creative_product = st.selectbox(
            "Selected product",
            product_labels,
            key="creative_selected_product",
        )
        selected_creative_product_id = selected_creative_product.split(" - ", 1)[0]
        creative_product = ranked_products[
            ranked_products["product_id"] == selected_creative_product_id
        ].iloc[0].to_dict()
        creative_offer = selected_recommended_offer(
            scored_offers,
            selected_creative_product_id,
        )
        creative_video_recommendation = selected_video_recommendation(
            video_recommendations,
            selected_creative_product_id,
        )

        summary_columns = st.columns(3)
        summary_columns[0].metric(
            "Product score",
            f"{creative_product['profit_potential_score']:.2f}",
        )
        summary_columns[1].metric(
            "Recommended offer",
            creative_offer["platform"] if creative_offer else "None",
        )
        evidence_label = (
            creative_video_recommendation.get("evidence_level")
            if creative_video_recommendation
            else "deterministic default"
        )
        summary_columns[2].metric("Video evidence", evidence_label)

        if creative_offer and creative_offer.get("offer_status") == "unknown":
            st.warning("The selected offer is marked unknown; verify it before use.")
        if creative_offer and creative_offer.get("offer_status") == "inactive":
            st.warning("Inactive offers are not promoted in Creative Studio drafts.")

        platform_options = list(PLATFORM_PRESETS)
        objective_options = list(CAMPAIGN_OBJECTIVES)
        input_columns = st.columns(2)
        with input_columns[0]:
            target_platform = st.selectbox(
                "Target platform",
                platform_options,
                key="creative_target_platform",
            )
            preset = PLATFORM_PRESETS[target_platform]
            campaign_objective = st.selectbox(
                "Campaign objective",
                objective_options,
                key="creative_campaign_objective",
            )
            if campaign_objective == "conversion-oriented promotion":
                st.warning(
                    "This changes structure and CTA emphasis only. It does not "
                    "predict conversion performance."
                )
            duration_seconds = st.selectbox(
                "Duration",
                ALLOWED_DURATIONS,
                index=ALLOWED_DURATIONS.index(preset["duration_seconds"]),
                key="creative_duration_seconds",
            )
            aspect_ratio = st.text_input(
                "Aspect ratio",
                value=preset["aspect_ratio"],
                key="creative_aspect_ratio",
            )
            pacing = st.text_input(
                "Pacing",
                value=preset["pacing"],
                key="creative_pacing",
            )
        with input_columns[1]:
            target_audience = st.text_input(
                "Target audience",
                value="interested buyers",
                key="creative_target_audience",
            )
            tone = st.text_input(
                "Tone",
                value="clear and helpful",
                key="creative_tone",
            )
            cta = st.text_input(
                "CTA",
                value=CAMPAIGN_OBJECTIVES[campaign_objective]["cta"],
                key="creative_cta",
            )
            template_override = st.selectbox(
                "Creative template",
                ["Auto", *CONTENT_TEMPLATES],
                key="creative_template_override",
            )
            hook_type_override = st.selectbox(
                "Hook type",
                [
                    "Auto",
                    "result first",
                    "problem solution",
                    "question",
                    "surprising fact",
                    "discount offer",
                    "general introduction",
                ],
                key="creative_hook_type_override",
            )

        default_feature = ""
        if creative_video_recommendation:
            feature_value = creative_video_recommendation.get("feature_to_emphasize")
            if feature_value and feature_value != "insufficient observations":
                default_feature = feature_value
        details_columns = st.columns(2)
        with details_columns[0]:
            key_product_features = st.text_area(
                "Key product features",
                value=default_feature,
                height=90,
                key="creative_key_product_features",
            )
            product_notes = st.text_area(
                "Product notes",
                height=90,
                key="creative_product_notes",
            )
        with details_columns[1]:
            brand_constraints = st.text_area(
                "Brand constraints",
                height=90,
                key="creative_brand_constraints",
            )
            include_disclosure = st.checkbox(
                "Include affiliate disclosure",
                value=True,
                key="creative_include_disclosure",
            )
            disclosure_text = st.text_input(
                "Disclosure text",
                value=DEFAULT_DISCLOSURE,
                key="creative_disclosure_text",
            )

        settings = {
            "target_platform": target_platform,
            "campaign_objective": campaign_objective,
            "duration_seconds": duration_seconds,
            "aspect_ratio": aspect_ratio,
            "pacing": pacing,
            "target_audience": target_audience,
            "tone": tone,
            "cta": cta,
            "template_override": template_override,
            "hook_type_override": hook_type_override,
            "key_product_features": key_product_features,
            "product_notes": product_notes,
            "brand_constraints": brand_constraints,
            "include_disclosure": include_disclosure,
            "disclosure_text": disclosure_text,
        }

        if st.session_state.get("creative_dirty"):
            st.warning(
                "You have edited the current creative draft. Generating again "
                "will replace the editable draft with a new baseline."
            )

        action_columns = st.columns(2)
        generate_clicked = action_columns[0].button("Generate creative package")
        reset_clicked = action_columns[1].button("Reset Creative Studio")
        if reset_clicked:
            reset_creative_state()
            st.rerun()

        if generate_clicked:
            package = build_creative_package(
                creative_product,
                offer=creative_offer,
                video_recommendation=creative_video_recommendation,
                settings=settings,
            )
            st.session_state.creative_baseline_package = package
            st.session_state.creative_baseline_script = package["script_text"]
            st.session_state.creative_baseline_storyboard = deepcopy(
                package["storyboard"]
            )
            st.session_state.creative_edited_script = package["script_text"]
            st.session_state.creative_dirty = False
            st.session_state.creative_last_settings = settings
            reset_video_generation_state()

        if "creative_baseline_package" in st.session_state:
            package = st.session_state.creative_baseline_package
            st.subheader("Video Brief")
            st.json(package["brief"])

            st.subheader("Editable Script")
            edited_script = st.text_area(
                "Script draft",
                value=st.session_state.get(
                    "creative_edited_script",
                    package["script_text"],
                ),
                height=280,
                key="creative_script_editor",
            )
            st.session_state.creative_edited_script = edited_script

            st.subheader("Editable Storyboard")
            storyboard_df = pd.DataFrame(package["storyboard"])
            edited_storyboard_df = st.data_editor(
                storyboard_df,
                width="stretch",
                num_rows="fixed",
                key="creative_storyboard_editor",
            )

            st.subheader("Generation Prompts")
            st.text_area(
                "Concise generation prompt",
                value=package["prompts"]["concise_generation_prompt"],
                height=90,
            )
            st.text_area(
                "Detailed generation prompt",
                value=package["prompts"]["detailed_generation_prompt"],
                height=160,
            )
            st.text_area(
                "Negative prompt",
                value=package["prompts"]["negative_prompt"],
                height=90,
            )

            edited_storyboard_records = edited_storyboard_df.to_dict("records")
            st.session_state.creative_dirty = (
                edited_script != st.session_state.creative_baseline_script
                or edited_storyboard_records
                != st.session_state.creative_baseline_storyboard
            )
            edited_package = edited_creative_package(
                edited_storyboard_df,
                edited_script,
            )
            if edited_package["validation_warnings"]:
                st.warning("; ".join(edited_package["validation_warnings"]))
            else:
                st.success("Creative package validation passed.")

            st.subheader("Exports")
            prompt_text = (
                edited_package["prompts"]["concise_generation_prompt"]
                + "\n\n"
                + edited_package["prompts"]["detailed_generation_prompt"]
                + "\n\nNegative prompt:\n"
                + edited_package["prompts"]["negative_prompt"]
            )
            download_columns = st.columns(4)
            download_columns[0].download_button(
                "Download video_brief.json",
                json_bytes(edited_package["brief"]),
                file_name="video_brief.json",
                mime="application/json",
            )
            download_columns[1].download_button(
                "Download video_brief.csv",
                brief_csv_bytes(edited_package["brief"]),
                file_name="video_brief.csv",
                mime="text/csv",
            )
            download_columns[2].download_button(
                "Download script.txt",
                text_bytes(edited_package["script_text"]),
                file_name="script.txt",
                mime="text/plain",
            )
            download_columns[3].download_button(
                "Download storyboard.csv",
                dataframe_csv_bytes(edited_package["storyboard"]),
                file_name="storyboard.csv",
                mime="text/csv",
            )

            second_download_columns = st.columns(4)
            second_download_columns[0].download_button(
                "Download storyboard.json",
                json_bytes(edited_package["storyboard"]),
                file_name="storyboard.json",
                mime="application/json",
            )
            second_download_columns[1].download_button(
                "Download generation_prompt.txt",
                text_bytes(prompt_text),
                file_name="generation_prompt.txt",
                mime="text/plain",
            )
            second_download_columns[2].download_button(
                "Download creative_package.json",
                json_bytes(edited_package),
                file_name="creative_package.json",
                mime="application/json",
            )
            second_download_columns[3].download_button(
                "Download complete_creative_package.zip",
                package_zip_bytes(edited_package),
                file_name="complete_creative_package.zip",
                mime="application/zip",
            )

with tabs[5]:
    st.subheader("Video Generator")
    st.caption(
        "Version 1.9A simulates the video-generation workflow with a local "
        "mock provider. The placeholder MP4 is not AI-generated and is not "
        "real market or creative output."
    )
    st.warning(
        "Mock output is simulated for workflow testing only. It must never be "
        "presented as an AI-generated video or as real provider output."
    )

    if "creative_baseline_package" not in st.session_state:
        st.write("Generate a Creative Studio package before using Video Generator.")
    else:
        package = st.session_state.creative_baseline_package
        request = build_video_generation_request(package)
        providers = get_video_provider_registry()
        provider_name = st.selectbox(
            "Video provider",
            list(providers),
            key="video_generation_provider",
        )
        provider = providers[provider_name]
        capabilities = provider.get_capabilities()

        summary_columns = st.columns(4)
        summary_columns[0].metric("Provider", capabilities.provider_name)
        summary_columns[1].metric("Model", provider.model_name)
        summary_columns[2].metric("Mode", "Text-to-video")
        summary_columns[3].metric("Cost", capabilities.cost_label)

        st.write("Provider Capabilities")
        st.json(dataclass_to_dict(capabilities))

        brief = package.get("brief", {})
        prompt = request.prompt
        prompt_columns = st.columns(2)
        prompt_columns[0].write("Creative Package")
        prompt_columns[0].json(
            {
                "product_name": brief.get("product_name", ""),
                "target_platform": brief.get("target_platform", ""),
                "duration_seconds": request.duration_seconds,
                "aspect_ratio": request.aspect_ratio,
            }
        )
        prompt_columns[1].write("Generation Prompt")
        prompt_columns[1].text_area(
            "Prompt sent to provider",
            value=prompt,
            height=220,
            disabled=True,
        )

        if package.get("validation_warnings"):
            st.warning("; ".join(package["validation_warnings"]))

        st.info(
            "Future real providers will require explicit confirmation before "
            "submitting any paid or external generation request. Version 1.9A "
            "uses only the local mock provider."
        )
        confirmed = st.checkbox(
            "I understand this is a simulated mock workflow.",
            key="video_generation_confirmed",
        )

        active_job = st.session_state.get("video_generation_job")
        duplicate_active = (
            active_job is not None
            and active_job.status in ACTIVE_VIDEO_STATUSES
            and st.session_state.get("video_generation_signature") == request.request_id
        )
        submit_disabled = not confirmed or duplicate_active

        action_columns = st.columns(3)
        submit_clicked = action_columns[0].button(
            "Submit mock generation job",
            disabled=submit_disabled,
        )
        refresh_clicked = action_columns[1].button(
            "Refresh job status",
            disabled=active_job is None,
        )
        cancel_clicked = action_columns[2].button(
            "Cancel job",
            disabled=active_job is None
            or active_job.status not in ACTIVE_VIDEO_STATUSES,
        )

        if duplicate_active:
            st.warning(
                "A job with the same request is already active. Refresh or "
                "cancel it before submitting again."
            )

        if submit_clicked:
            job, result, error = submit_video_generation(provider, request)
            st.session_state.video_generation_request = request
            st.session_state.video_generation_signature = request.request_id
            st.session_state.video_generation_job = job
            st.session_state.video_generation_result = result
            st.session_state.video_generation_error = error
            active_job = job

        if refresh_clicked and active_job is not None:
            job, result, error = refresh_video_generation(provider, active_job)
            st.session_state.video_generation_job = job
            st.session_state.video_generation_result = result
            st.session_state.video_generation_error = error
            active_job = job

        if cancel_clicked and active_job is not None:
            job = cancel_video_generation(provider, active_job)
            st.session_state.video_generation_job = job
            st.session_state.video_generation_error = None
            active_job = job

        current_job = st.session_state.get("video_generation_job")
        current_error = st.session_state.get("video_generation_error")
        current_result = st.session_state.get("video_generation_result")

        if current_job is None:
            st.write("No video generation job has been submitted yet.")
        else:
            st.subheader("Job Status")
            status_columns = st.columns(4)
            status_columns[0].metric("Status", current_job.status)
            status_columns[1].metric(
                "Progress",
                f"{(current_job.progress or 0) * 100:.0f}%",
            )
            status_columns[2].metric("Provider", current_job.provider)
            status_columns[3].metric("Model", current_job.model)
            st.write(current_job.message)
            st.json(dataclass_to_dict(current_job))

        if current_error is not None:
            st.error(current_error.message)
            st.json(dataclass_to_dict(current_error))

        if current_result is not None and current_job.status == VIDEO_STATUS_COMPLETED:
            st.subheader("Mock MP4 Preview")
            st.info(
                "This preview is a locally generated placeholder MP4 for "
                "workflow testing. It is not AI-generated."
            )
            video_path = Path(current_result.local_video_path)
            video_bytes = video_path.read_bytes()
            st.video(video_bytes)
            product_name = brief.get("product_name", "mock-video")
            download_name = f"{safe_filename(product_name)}-mock-placeholder.mp4"
            st.download_button(
                "Download mock placeholder MP4",
                video_bytes,
                file_name=download_name,
                mime="video/mp4",
            )

with tabs[6]:
    st.subheader("Data Quality")
    quality_metrics = st.columns(6)
    quality_metrics[0].metric("Excluded products", len(excluded_products))
    quality_metrics[1].metric("Excluded offers", len(excluded_offers))
    quality_metrics[2].metric("Provider failures", len(failed_provider_df))
    quality_metrics[3].metric("Excluded videos", len(excluded_videos))
    quality_metrics[4].metric("Video warnings", len(video_warnings))
    quality_metrics[5].metric("Text warnings", len(video_text_warnings))

    if not excluded_products.empty:
        st.write("Excluded Product Records")
        st.dataframe(excluded_products, width="stretch")
        st.download_button(
            "Download excluded products",
            excluded_products.to_csv(index=False).encode("utf-8"),
            file_name="excluded_products.csv",
            mime="text/csv",
        )
    if not excluded_offers.empty:
        st.write("Excluded Offer Records")
        st.dataframe(excluded_offers, width="stretch")
        st.download_button(
            "Download excluded offers",
            excluded_offers.to_csv(index=False).encode("utf-8"),
            file_name="excluded_offers.csv",
            mime="text/csv",
        )
    if not failed_provider_df.empty:
        st.write("Failed Provider Records")
        st.dataframe(failed_provider_df, width="stretch")
    if not excluded_videos.empty:
        st.write("Excluded Video Records")
        st.dataframe(excluded_videos, width="stretch")
        st.download_button(
            "Download excluded video records",
            excluded_videos.to_csv(index=False).encode("utf-8"),
            file_name="excluded_videos.csv",
            mime="text/csv",
        )
    if not video_warnings.empty:
        st.write("Video Data Warnings")
        st.dataframe(video_warnings, width="stretch")
        st.download_button(
            "Download video warning report",
            video_warnings.to_csv(index=False).encode("utf-8"),
            file_name="video_warnings.csv",
            mime="text/csv",
        )
    if not video_text_warnings.empty:
        st.write("Video Text Warnings")
        st.dataframe(video_text_warnings, width="stretch")
        st.download_button(
            "Download video text warning report",
            video_text_warnings.to_csv(index=False).encode("utf-8"),
            file_name="video_text_warnings.csv",
            mime="text/csv",
        )
    if (
        excluded_products.empty
        and excluded_offers.empty
        and excluded_videos.empty
        and video_warnings.empty
        and video_text_warnings.empty
        and failed_provider_df.empty
        and products_input is not None
    ):
        st.success("No records were excluded.")

with tabs[7]:
    st.subheader("Scalability")
    product_rows = len(products_input) if products_input is not None else 0
    offer_rows = len(offers_input) if offers_input is not None else 0
    video_rows = len(videos_input) if videos_input is not None else 0
    total_rows = product_rows + offer_rows + video_rows
    average_ms = timings["total"] / total_rows * 1000 if total_rows else 0
    scalability_metrics = st.columns(5)
    scalability_metrics[0].metric("Rows processed", total_rows)
    scalability_metrics[1].metric("Valid products", len(valid_products))
    scalability_metrics[2].metric("Valid offers", len(valid_offers))
    scalability_metrics[3].metric("Valid videos", len(valid_videos))
    scalability_metrics[4].metric(
        "Excluded",
        len(excluded_products)
        + len(excluded_offers)
        + len(excluded_videos)
        + len(failed_provider_df),
    )
    st.dataframe(
        pd.DataFrame(
            [
                {"stage": key.replace("_", " ").title(), "seconds": value}
                for key, value in timings.items()
            ]
        ),
        width="stretch",
    )
    st.metric("Average processing time per input record", f"{average_ms:.3f} ms")
    st.write(
        "Download readiness:",
        "Ready" if not ranked_products.empty else "Waiting for valid product results",
    )
    if products_input is not None:
        st.success("Processing completed successfully.")

with tabs[8]:
    st.subheader("Methodology")
    st.markdown(
        f"""
### Five Separate Decision Layers

- **Product Opportunity Score** estimates short-term market opportunity.
- **Platform Offer Score** compares affiliate economics for the same product.
- **Video Insights** compare observed attention and engagement patterns.
- **Creative Studio** turns existing context into editable video planning
  artifacts.
- **Video Generator** tests a provider-neutral job workflow with a mock
  placeholder MP4.

Video Insights do not create a score, conversion estimate, revenue estimate, or
profit prediction.

### Product Scoring

The Version 1.2 formula and caps remain unchanged. Reference product economics
use `reference_price` and `reference_commission_rate`. Product weights are:
`{SCORING_CONFIG["weights"]}`.

### Offer Commission Value

- `one_time` and `recurring`: `offer_price × commission_rate`
- `fixed_amount`: `fixed_commission_amount`
- `lead`: `commission_per_lead`

Percentage offers require `0 < commission_rate <= 1`. Recurring payout type
requires a true recurring flag; all other types require false.

### Offer Scoring

Caps: `{OFFER_SCORING_CONFIG["caps"]}`

Percentage weights: `{OFFER_SCORING_CONFIG["percentage_weights"]}`

Fixed/lead weights: `{OFFER_SCORING_CONFIG["fixed_lead_weights"]}`

Fixed and lead offers receive no commission-rate or recurring contribution.
Inactive offers are never recommended. Unknown offers are recommended only when
no active offer exists.

### Video Metrics And Evidence

Engagement rate is calculated only when likes, comments, shares, and positive
views are all available. Missing values remain unknown. Product-level
recommendations require at least five valid videos, three with positive views,
and two valid observations per candidate. Category fallback requires at least
ten videos from three products and three observations per candidate.

### Video Text Intelligence

Version 1.6 can enrich uploaded video rows with optional `description`,
`transcript`, `hashtags`, `creator_name`, and `language` fields. Text analysis
uses transparent rule-based matching for content format, hook type, CTA
detection, and product-feature extraction. It does not use LLM APIs,
supervised ML, sentiment analysis, clustering, scraping, or video downloads.

Detected labels do not silently overwrite manual labels. The safest default is
manual first with detected fallback, and agreement reports are consistency
checks rather than accuracy claims.

### Creative Studio

Version 1.8 creates provider-neutral planning artifacts: a video brief,
timestamped script, editable storyboard, generation prompts, creative-package
JSON, and a ZIP export. It uses product-level video recommendations first,
category-level recommendations second, and deterministic objective-based
templates when evidence is insufficient.

User overrides win. Inactive offers are excluded from promotion planning.
Unknown offers require a warning. Commission and cookie-duration terms are
internal affiliate economics and are not written into consumer-facing script
text by default. Unsupported claims such as guaranteed results, best-product
claims, invented discounts, health/safety claims, and specific savings are
flagged for review.

### Video Generator

Version 1.9A adds provider-neutral request, job, result, error, and capability
models plus a deterministic mock provider. The mock provider uses manual status
refresh, prevents duplicate active submissions, supports cancellation, and
creates a temporary placeholder MP4 for preview and download.

The placeholder MP4 is simulated workflow output. It is not AI-generated, not
real provider output, and not evidence that a product will perform well.

### Limitations

All caps and weights are provisional. Mock-provider and generated files are
synthetic. Version 1.9A performs no URL requests, scraping, remote video
downloading, semantic computer vision, audio analysis, external LLM calls,
real AI video generation, image generation, audio generation, paid provider
jobs, conversion prediction, revenue prediction, or automated posting.

Future versions may integrate real affiliate APIs, persistent storage,
historical outcome data, and separately approved analytical capabilities.
"""
    )
