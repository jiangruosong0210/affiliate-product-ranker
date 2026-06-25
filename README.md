# Affiliate Product Ranker MVP

## Project Overview

Affiliate Product Ranker Version 1.4 supports two independent decisions:

1. Which products have the strongest short-term market opportunity?
2. For the same product, which platform-specific affiliate offer is most
   attractive?

The Product Opportunity Score from Versions 1.2 and 1.3A remains unchanged.
Version 1.4 adds a separate Platform Offer Score. The scores are not combined
into a final profit prediction.

This is a rule-based demonstration and decision-support tool. It does not
guarantee affiliate revenue or profit.

Version 1.4 does not use real APIs, scraping, databases, machine learning, LLM
APIs, computer vision, or video analysis.

## Two-File Model

### Products

`products.csv` represents products and their market opportunity.

Required core columns:

```text
product_id
product_name
category
product_type
product_url
reference_price
reference_commission_rate
```

Manual mode also requires:

```text
search_volume
search_growth_7d
social_mentions_7d
competitor_count
days_until_peak
seasonal_relevance
```

Automatic mock mode requires only the core columns. The six market signals are
optional row-level fallback values.

`reference_price` and `reference_commission_rate` are provisional product-level
inputs used only to preserve the existing Product Opportunity Score. They are
separate from real platform-offer economics.

`product_id` must be non-empty and unique. Rows participating in a duplicate ID
are excluded because offer relationships would otherwise be ambiguous.

### Platform Offers

`offers.csv` represents affiliate terms offered by individual platforms:

```text
offer_id
product_id
platform
payout_type
offer_price
commission_rate
fixed_commission_amount
commission_per_lead
cookie_duration_days
recurring_commission
affiliate_url
offer_status
```

Valid payout types:

```text
one_time
recurring
fixed_amount
lead
```

Valid offer statuses:

```text
active
inactive
unknown
```

An offers upload is optional. Product ranking continues to work without it.

## Application Modes

### Manual CSV

Manual mode uses the complete product schema and reads the six uploaded market
signals through `ManualProvider`.

### Mock Automatic Data

Mock mode generates deterministic synthetic signals from rule-based keywords.
It is an architecture test, not real market data.

If mock retrieval fails, valid optional CSV signals can be used as fallback.
A failed product without fallback is excluded without stopping other products.

Keyword generation uses product name and category. Affiliate platform names are
not included in buyer-demand search queries.

## Product Opportunity Score

The Version 1.2 caps and formulas are unchanged:

```text
maximum search volume: 100,000
maximum social mentions: 10,000
maximum competitor count: 100
growth range: -50% to +50%
maximum days until peak: 60
maximum reference commission per sale: $50
```

```text
reference commission per sale =
  reference_price * reference_commission_rate

Product Opportunity Score =
  commission_score * 0.30
  + trend_score * 0.25
  + demand_score * 0.20
  + competition_opportunity * 0.15
  + urgency_score * 0.10
```

## Payout-Specific Commission Values

### One-Time And Recurring

```text
commission_value = offer_price * commission_rate
offer_price > 0
0 < commission_rate <= 1
```

### Fixed Amount

```text
commission_value = fixed_commission_amount
fixed_commission_amount > 0
```

### Lead

```text
commission_value = commission_per_lead
commission_per_lead > 0
```

Non-applicable payout fields may be blank.

Recurring consistency is strict:

```text
payout_type == recurring → recurring_commission must be true
all other payout types   → recurring_commission must be false
```

Contradictory rows are excluded.

## Platform Offer Score

All assumptions are stored in `OFFER_SCORING_CONFIG`.

Reference caps:

```text
commission value: $100
commission rate: 50%
cookie duration: 90 days
```

Component mappings:

```text
commission_value_score =
  clip(commission_value / 100 * 100, 0, 100)

commission_rate_score =
  clip(commission_rate / 0.50 * 100, 0, 100)

cookie_duration_score =
  clip(cookie_duration_days / 90 * 100, 0, 100)

recurring_score:
  true = 100
  false = 0

status_score:
  active = 100
  unknown = 50
  inactive = 0
```

Percentage-based offer weights:

```text
commission value: 0.40
commission rate: 0.20
cookie duration: 0.15
recurring commission: 0.15
offer status: 0.10
```

For fixed and lead offers, commission rate and recurring commission are
inapplicable. Their weights are redistributed proportionally:

```text
commission value: 0.6153846154
cookie duration: 0.2307692308
offer status: 0.1538461538
total: 1.0
```

Fixed and lead offers receive zero commission-rate and recurring contributions.

## Offer Recommendations

For each product:

1. Recommend the highest-scoring active offer.
2. If no active offer exists, recommend the highest-scoring unknown offer and
   display a warning.
3. Never recommend an inactive offer.
4. Resolve ties using commission value, cookie duration, then `offer_id`.

## Validation And Exclusions

Product and offer rows are validated independently. Validation reports all
detectable reasons for each excluded row.

Checks include:

- missing required fields
- duplicate product or offer IDs
- orphan offers
- invalid payout types
- invalid offer statuses
- invalid commission rates
- missing payout-specific amounts
- negative cookie duration
- invalid recurring booleans
- payout and recurring-flag contradictions

Excluded records remain downloadable from the Data Quality tab. One invalid
offer does not prevent valid offers from being scored.

## Dashboard Tabs

1. **Overview**: counts, provider status, top product, recommended offer, timing.
2. **Product Ranking**: existing ranking, filters, Top N, chart, and download.
3. **Platform Offer Comparison**: offer filters and side-by-side product offers.
4. **Data Quality**: excluded records, reasons, and error-report downloads.
5. **Scalability**: row counts and processing-stage timing.
6. **Methodology**: formulas, assumptions, limitations, and future work.

## Synthetic Test Data

Run:

```bash
python generate_test_data.py
```

The generator uses fixed seed `140`.

Clean scalability files:

```text
large_sample_products.csv: exactly 1,000 valid products
large_sample_offers.csv: exactly 2,500 valid offers
```

Validation-only files:

```text
invalid_sample_products.csv
invalid_sample_offers.csv
```

The clean files contain no intentional validation errors. Invalid examples are
kept separately and include duplicates, orphans, bad rates, missing payout
values, invalid booleans, payout types, and statuses.

All generated data is synthetic test data and does not represent real affiliate
markets.

## Local Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
streamlit run app.py
```

## Tests

```bash
python -m unittest discover -s tests
```

Tests cover Versions 1.2, 1.3A, and 1.4, including the complete clean
1,000-product and 2,500-offer run.

## Repository Structure

```text
affiliate-product-ranker/
├── app.py
├── data_quality.py
├── generate_test_data.py
├── keyword_generation.py
├── offer_scoring.py
├── schemas.py
├── scoring.py
├── signal_processing.py
├── validation.py
├── market_data/
├── sample_products.csv
├── sample_offers.csv
├── large_sample_products.csv
├── large_sample_offers.csv
├── invalid_sample_products.csv
├── invalid_sample_offers.csv
├── tests/
├── requirements.txt
└── README.md
```

## Streamlit Community Cloud

```text
Repository: <your-github-username>/<your-repository-name>
Branch: main
Entrypoint: app.py
Python: 3.12
Secrets: none
```

Future versions may add real affiliate APIs, a database, historical
machine-learning models, and a separate video-analysis module. None are included
in Version 1.4.
