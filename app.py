import html
from pathlib import Path
from time import perf_counter

import pandas as pd
import streamlit as st

from data_quality import validate_offer_records, validate_product_records
from market_data.manual_provider import ManualProvider
from market_data.mock_provider import MockProvider
from market_data.service import process_market_data
from offer_scoring import OFFER_SCORING_CONFIG, score_offers
from scoring import SCORING_CONFIG, score_products


PROJECT_DIR = Path(__file__).resolve().parent
PRODUCT_TEMPLATE_PATH = PROJECT_DIR / "sample_products.csv"
OFFER_TEMPLATE_PATH = PROJECT_DIR / "sample_offers.csv"


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


st.set_page_config(page_title="Affiliate Product Ranker", layout="wide")
st.title("Affiliate Product Ranker")
st.write(
    "Compare product market opportunity and platform-specific affiliate offers "
    "for the next 7-30 days."
)
st.info(
    "Version 1.4 keeps Product Opportunity Score and Platform Offer Score "
    "separate because they answer different decisions."
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

upload_columns = st.columns(2)
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

products_input, product_read_error = read_uploaded_csv(products_file)
offers_input, offer_read_error = read_uploaded_csv(offers_file)

for read_error in [product_read_error, offer_read_error]:
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
timings = {
    "product_validation": 0.0,
    "provider_processing": 0.0,
    "product_scoring": 0.0,
    "offer_validation": 0.0,
    "offer_scoring": 0.0,
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

timings["total"] = perf_counter() - processing_started

tabs = st.tabs(
    [
        "Overview",
        "Product Ranking",
        "Platform Offer Comparison",
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
        overview_metrics = st.columns(5)
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
        overview_metrics[4].metric(
            "Excluded records",
            len(excluded_products) + len(excluded_offers) + len(failed_provider_df),
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
    st.subheader("Data Quality")
    quality_metrics = st.columns(3)
    quality_metrics[0].metric("Excluded products", len(excluded_products))
    quality_metrics[1].metric("Excluded offers", len(excluded_offers))
    quality_metrics[2].metric("Provider failures", len(failed_provider_df))

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
    if (
        excluded_products.empty
        and excluded_offers.empty
        and failed_provider_df.empty
        and products_input is not None
    ):
        st.success("No records were excluded.")

with tabs[4]:
    st.subheader("Scalability")
    product_rows = len(products_input) if products_input is not None else 0
    offer_rows = len(offers_input) if offers_input is not None else 0
    total_rows = product_rows + offer_rows
    average_ms = timings["total"] / total_rows * 1000 if total_rows else 0
    scalability_metrics = st.columns(4)
    scalability_metrics[0].metric("Rows processed", total_rows)
    scalability_metrics[1].metric("Valid products", len(valid_products))
    scalability_metrics[2].metric("Valid offers", len(valid_offers))
    scalability_metrics[3].metric(
        "Excluded",
        len(excluded_products) + len(excluded_offers) + len(failed_provider_df),
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

with tabs[5]:
    st.subheader("Methodology")
    st.markdown(
        f"""
### Two Separate Decision Layers

- **Product Opportunity Score** estimates short-term market opportunity.
- **Platform Offer Score** compares affiliate economics for the same product.

They are not combined into a final profit prediction.

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

### Limitations

All caps and weights are provisional. Mock-provider and generated files are
synthetic. Version 1.4 uses no real APIs, scraping, database, machine learning,
LLM, or video analysis.

Future versions may integrate real affiliate APIs, persistent storage,
historical outcome data, machine learning, and a separate video-analysis layer.
"""
    )
