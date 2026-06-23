import html
from pathlib import Path

import pandas as pd
import streamlit as st

from scoring import score_products
from validation import REQUIRED_COLUMNS, validate_products


PROJECT_DIR = Path(__file__).resolve().parent
SAMPLE_CSV_PATH = PROJECT_DIR / "sample_products.csv"


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
            delta=f"${product['commission_potential']:.2f} commission potential",
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
    "This MVP uses a transparent scoring formula. The results are estimates, "
    "not guaranteed profit."
)
st.warning(
    "This application provides estimated product opportunity scores for "
    "demonstration and decision-support purposes only. It does not guarantee "
    "affiliate revenue or profit."
)
st.caption(
    "Version 1.1 keeps fixed scoring weights as provisional MVP assumptions. "
    "Future versions may learn or optimize weights from historical performance "
    "data and machine learning."
)

with st.expander("Required CSV columns", expanded=True):
    st.code("\n".join(REQUIRED_COLUMNS), language="text")

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
        errors = validate_products(products_df)

        if errors:
            st.error("Please fix these issues before ranking products:")
            for error in errors:
                st.write(f"- {error}")
        else:
            st.subheader("Uploaded Product Data")
            st.dataframe(products_df, width="stretch")

            ranked_df = score_products(products_df)
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
                    "price",
                    "commission_rate",
                    "commission_potential",
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
