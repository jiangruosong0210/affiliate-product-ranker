# Affiliate Product Ranker MVP

## Project Overview

Affiliate Product Ranker is a beginner-friendly Streamlit Version 1.1 app. It
ranks affiliate products by estimated short-term opportunity for the next 7-30
days using a transparent, rule-based scoring formula.

This is a decision-support MVP, not a guaranteed profit prediction tool. Its
scores are estimates and do not guarantee affiliate revenue or profit. Version
1.1 does not use affiliate APIs, web scraping, paid APIs, machine learning,
databases, authentication, LangChain, CrewAI, or any other agent framework.

## What The App Does

The app lets you upload a CSV file of affiliate products or download the sample
CSV template. It checks that the CSV has the right columns, calculates a score
from 0 to 100, ranks the products from highest to lowest opportunity, explains
the ranking, and lets you download the ranked results.

Version 1.1 also includes:

- a platform filter
- a category filter
- a Top N selector
- a Top 3 summary section
- a score chart for the selected Top N products
- a contribution breakdown for each scored product

## Required CSV Columns

Your CSV must include these columns:

```text
product_name
platform
category
price
commission_rate
trend_score
demand_score
competition_score
urgency_score
product_url
```

Only `product_name`, `platform`, and `category` must contain non-empty text.
`product_url` is required as a column, but individual values may be empty.

## Value Rules

- `price` must be greater than 0.
- `commission_rate` must be between 0 and 1.
- Enter `commission_rate` as a decimal, such as `0.20` for 20%.
- `trend_score`, `demand_score`, `competition_score`, and `urgency_score` must
  be between 0 and 100.
- Lower `competition_score` is better.

## Scoring Formula

First, the app calculates raw commission potential:

```text
commission_potential = price * commission_rate
```

Then it normalizes commission potential to a 0-100 scale relative to the
products in the currently uploaded CSV:

```text
normalized_commission =
  ((commission_potential - minimum_commission_potential)
  / (maximum_commission_potential - minimum_commission_potential)) * 100
```

If every product has the same commission potential, every product receives a
normalized commission value of 50.

This means scores from two different uploaded datasets may not be directly
comparable. A product's commission score depends on the other products in the
same CSV upload.

The app reverses competition because lower competition is better:

```text
competition_opportunity = 100 - competition_score
```

The final score is:

```text
profit_potential_score =
  (normalized_commission * 0.30)
+ (trend_score * 0.25)
+ (demand_score * 0.20)
+ (competition_opportunity * 0.15)
+ (urgency_score * 0.10)
```

These weights are fixed internal MVP assumptions:

```text
commission: 0.30
trend: 0.25
demand: 0.20
competition: 0.15
urgency: 0.10
```

Users cannot manually change these weights in Version 1.1. They are
provisional, meaning they are reasonable starting assumptions rather than proven
business truths. Future versions may use historical outcome data and machine
learning to estimate better weights.

## Explanation Logic

The app calculates each factor's weighted contribution:

```text
commission_contribution = normalized_commission * 0.30
trend_contribution = trend_score * 0.25
demand_contribution = demand_score * 0.20
competition_contribution = competition_opportunity * 0.15
urgency_contribution = urgency_score * 0.10
```

Each explanation uses the top two or three positive contributions. When a clear
weakness exists, such as high competition or weak urgency, the explanation
mentions it.

The explanation format is:

```text
Strengths: ...
Risk: ...
Action: ...
```

The action is a simple recommendation, such as testing with a small campaign
before scaling.

## Filters And Top N

After uploading a valid CSV, use the sidebar to filter products by platform and
category. The Top N selector controls how many ranked products appear in the
chart, table, and downloaded results.

Filtering does not change the scoring formula. It only narrows which already
scored products are shown.

## Contribution Breakdown

The ranked table includes these columns:

```text
commission_contribution
trend_contribution
demand_contribution
competition_contribution
urgency_contribution
```

These columns show how much each factor added to the final score. For example,
if a product has a high `trend_contribution`, the current trend score is helping
that product's ranking.

## Local Setup

Python 3.12 is recommended because it is the current default on Streamlit
Community Cloud.

Create and activate a virtual environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Run the app:

```bash
streamlit run app.py
```

Then open the local URL shown in your terminal.

## Try The Sample CSV

This project includes `sample_products.csv`. Upload it in the Streamlit app to
see the MVP ranking workflow.

## Required GitHub Repository Structure

Keep these files in the repository root:

```text
affiliate-product-ranker/
├── .gitignore
├── app.py
├── scoring.py
├── validation.py
├── sample_products.csv
├── requirements.txt
└── README.md
```

The running application depends only on `app.py`, `scoring.py`,
`validation.py`, `sample_products.csv`, and the packages in
`requirements.txt`. The README documents the project, and `.gitignore` prevents
local environments, caches, output folders, and secret files from being
committed.

## Deploy To Streamlit Community Cloud

1. Create a new GitHub repository, but keep it private until you have reviewed
   the project.
2. Push the files in the repository structure above to the `main` branch.
3. Sign in at [Streamlit Community Cloud](https://share.streamlit.io/).
4. Select **Create app**, then choose the option for an existing app.
5. Enter your GitHub repository, branch, and entrypoint file.
6. Open **Advanced settings** and select Python 3.12.
7. No secrets or environment variables are required for this app.
8. Review the settings, then deploy only when you are ready.

Use these Streamlit Community Cloud settings:

```text
Repository: <your-github-username>/<your-repository-name>
Branch: main
Entrypoint file: app.py
Python version: 3.12
```

The app reads `sample_products.csv` relative to the project directory, so the
template download works both locally and on Streamlit Community Cloud.
