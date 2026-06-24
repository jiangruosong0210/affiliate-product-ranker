import html
from pathlib import Path

import pandas as pd
import streamlit as st

from market_data.manual_provider import ManualProvider
from market_data.mock_provider import MockProvider
from market_data.service import process_market_data
from scoring import score_products
from signal_processing import SIGNAL_CONFIG
from validation import CORE_COLUMNS, REQUIRED_COLUMNS, SIGNAL_COLUMNS, validate_products


PROJECT_DIR = Path(__file__).resolve().parent
SAMPLE_CSV_PATH = PROJECT_DIR / "sample_products.csv"


@st.cache_resource
def get_provider_registry():
    return {
        "Manual CSV": ManualProvider(),
        "Mock automatic data": MockProvider(),
    }


def apply_sidebar_filters(ranked_df):
    st.sidebar.header("Filters")

    platforms = sorted(ranked_df["platform"].dropna().unique())
    categories = sorted(ranked_df["category"].dropna().unique())

    selected_platforms = st.sidebar.multiselect(
        "Platform",
        options=platforms,
        default=platforms,
    )
    selected_categories = st.sidebar.multiselect(
        "Category",
        options=categories,
        default=categories,
    )

    return ranked_df[
        ranked_df["platform"].isin(selected_platforms)
        & ranked_df["category"].isin(selected_categories)
    ]


def show_top_three(top_three_df):
    columns = st.columns(3)

    for index, column in enumerate(columns):
        if index >= len(top_three_df):
            column.empty()
            continue

        product = top_three_df.iloc[index]
        column.metric(
            label=f"#{int(product['rank'])} {product['product_name']}",
            value=f"{product['profit_potential_score']:.2f}",
            delta=f"${product['commission_per_sale']:.2f} commission per sale",
        )
        column.caption(product["platform"])


def show_score_bar_chart(top_n_df):
    chart_df = top_n_df[["product_name", "profit_potential_score"]].copy()
    maximum_score = max(chart_df["profit_potential_score"].max(), 1)

    chart_html = ""
    for _, row in chart_df.iterrows():
        width = (row["profit_potential_score"] / maximum_score) * 100
        product_name = html.escape(str(row["product_name"]))
        score = row["profit_potential_score"]
        chart_html += f"""
        <div style="margin-bottom: 0.75rem;">
            <div style="display: flex; justify-content: space-between; gap: 1rem;">
                <span>{product_name}</span>
                <strong>{score:.2f}</strong>
            </div>
            <div style="background: #eee; height: 0.75rem; border-radius: 0.25rem;">
                <div style="background: #4f8bf9; width: {width:.2f}%; height: 0.75rem; border-radius: 0.25rem;"></div>
            </div>
        </div>
        """

    st.markdown(chart_html, unsafe_allow_html=True)


st.set_page_config(page_title="Affiliate Product Ranker", layout="wide")

st.title("Affiliate Product Ranker")
st.write(
    "Upload a CSV file to rank affiliate products by estimated short-term "
    "opportunity for the next 7-30 days."
)
st.info(
    "Version 1.3A adds deterministic keyword generation and a provider-based "
    "market-data workflow while keeping all Version 1.2 scoring formulas."
)
st.warning(
    "This application provides estimated product opportunity scores for "
    "demonstration and decision-support purposes only. It does not guarantee "
    "affiliate revenue or profit."
)
st.caption(
    "Version 1.3A keeps fixed scoring weights and reference caps as provisional "
    "MVP assumptions. "
    "Future versions may learn or optimize weights from historical performance "
    "data and machine learning."
)

mode = st.radio(
    "Market data mode",
    options=["Manual CSV", "Mock automatic data"],
    horizontal=True,
)
validation_mode = "manual" if mode == "Manual CSV" else "automatic"

if mode == "Mock automatic data":
    st.warning(
        "Mock automatic mode uses deterministic synthetic test values. These "
        "values are not real market data and must not be used as evidence of "
        "actual demand, competition, or profit potential."
    )

with st.expander("Required CSV columns", expanded=True):
    required_columns = REQUIRED_COLUMNS if validation_mode == "manual" else CORE_COLUMNS
    st.code("\n".join(required_columns), language="text")
    if validation_mode == "automatic":
        st.caption(
            "The six raw-signal columns are optional in automatic mode. When all "
            "six are valid for a product, they can be used as fallback data."
        )
        st.code("\n".join(SIGNAL_COLUMNS), language="text")

with st.expander("How raw signals become scores"):
    st.markdown(
        f"""
- **Commission score:** `price × commission_rate`, capped at
  `${SIGNAL_CONFIG["max_commission_per_sale"]}` per sale.
- **Trend score:** 7-day search growth maps from
  `{SIGNAL_CONFIG["max_negative_growth"]}% = 0` through `0% = 50` to
  `+{SIGNAL_CONFIG["max_positive_growth"]}% = 100`.
- **Demand score:** 70% search volume and 30% social mentions, using fixed caps
  of `{SIGNAL_CONFIG["max_search_volume"]:,}` searches and
  `{SIGNAL_CONFIG["max_social_mentions"]:,}` mentions.
- **Competition score:** competitor count maps from `0 = 0` to
  `{SIGNAL_CONFIG["max_competitor_count"]}+ = 100`; lower is better.
- **Urgency score:** 60% timing urgency and 40% seasonal relevance. Timing maps
  from `0 days = 100` to `{SIGNAL_CONFIG["max_days_until_peak"]}+ days = 0`.

Values outside a reference range are clipped to 0 or 100. These fixed caps make
derived scores more stable across different CSV uploads.
"""
    )

with SAMPLE_CSV_PATH.open("rb") as template_file:
    template_data = template_file.read()
    st.download_button(
        label="Download CSV Template",
        data=template_data,
        file_name="sample_products.csv",
        mime="text/csv",
    )

uploaded_file = st.file_uploader("Upload your product CSV", type=["csv"])

if uploaded_file is None:
    st.write("Upload a CSV file to begin.")
else:
    try:
        products_df = pd.read_csv(uploaded_file)
    except Exception as exc:
        st.error(f"Could not read the CSV file: {exc}")
    else:
        errors = validate_products(products_df, mode=validation_mode)

        if errors:
            st.error("Please fix these issues before ranking products:")
            for error in errors:
                st.write(f"- {error}")
        else:
            st.subheader("Uploaded Product Data")
            st.dataframe(products_df, width="stretch")

            providers = get_provider_registry()
            if "provider_result_cache" not in st.session_state:
                st.session_state.provider_result_cache = {}

            result_cache = (
                st.session_state.provider_result_cache
                if mode == "Mock automatic data"
                else {}
            )
            signal_df, failed_df = process_market_data(
                products_df,
                providers[mode],
                result_cache=result_cache,
            )

            status_frames = []
            if not signal_df.empty:
                status_frames.append(signal_df)
            if not failed_df.empty:
                status_frames.append(failed_df)

            st.subheader("Market Data Status")
            status_df = pd.concat(status_frames, ignore_index=True)
            status_columns = [
                "product_name",
                "primary_keyword",
                "data_source",
                "retrieval_status",
                "confidence_level",
                "retrieved_at",
                "error_message",
            ]
            st.dataframe(status_df[status_columns], width="stretch")

            if not failed_df.empty:
                st.warning(
                    f"{len(failed_df)} product(s) could not retrieve valid market "
                    "data and had no valid CSV fallback. They were excluded from "
                    "scoring; other products were processed normally."
                )

            if signal_df.empty:
                st.error("No products have valid market signals available for scoring.")
                st.stop()

            ranked_df = score_products(signal_df)

            st.subheader("Derived Signal Scores")
            derived_columns = [
                "product_name",
                "data_source",
                "retrieval_status",
                "commission_per_sale",
                "commission_score",
                "trend_score",
                "demand_score",
                "competition_score",
                "competition_opportunity",
                "urgency_score",
            ]
            st.dataframe(ranked_df[derived_columns], width="stretch")

            filtered_df = apply_sidebar_filters(ranked_df)

            if filtered_df.empty:
                st.warning("No products match the selected filters.")
            else:
                top_n = st.sidebar.number_input(
                    "Top N products",
                    min_value=1,
                    max_value=len(filtered_df),
                    value=min(5, len(filtered_df)),
                    step=1,
                )
                top_n_df = filtered_df.head(top_n)

                st.subheader("Top 3 Products")
                show_top_three(top_n_df.head(3))

                st.subheader(f"Top {top_n} Score Chart")
                show_score_bar_chart(top_n_df)

                st.subheader("Ranked Products")
                display_columns = [
                    "rank",
                    "product_name",
                    "platform",
                    "category",
                    "primary_keyword",
                    "related_keywords",
                    "search_queries",
                    "data_source",
                    "retrieved_at",
                    "confidence_level",
                    "retrieval_status",
                    "error_message",
                    "price",
                    "commission_rate",
                    "commission_per_sale",
                    "commission_score",
                    "search_volume",
                    "search_growth_7d",
                    "social_mentions_7d",
                    "competitor_count",
                    "days_until_peak",
                    "seasonal_relevance",
                    "trend_score",
                    "demand_score",
                    "competition_score",
                    "competition_opportunity",
                    "urgency_score",
                    "profit_potential_score",
                    "commission_contribution",
                    "trend_contribution",
                    "demand_contribution",
                    "competition_contribution",
                    "urgency_contribution",
                    "explanation",
                    "product_url",
                ]
                st.dataframe(top_n_df[display_columns], width="stretch")

                csv_data = top_n_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="Download ranked results as CSV",
                    data=csv_data,
                    file_name="ranked_affiliate_products.csv",
                    mime="text/csv",
                )
