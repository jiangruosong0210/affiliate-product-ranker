# Affiliate Product Ranker MVP

## Project Overview

Affiliate Product Ranker is a beginner-friendly Streamlit Version 1.3A app. It
ranks affiliate products by estimated short-term opportunity for the next 7-30
days.

Version 1.3A adds deterministic keyword generation and a provider-based
market-data architecture. It does not use paid APIs, web scraping, databases,
authentication, machine learning, LangChain, CrewAI, or an LLM API.

The Version 1.2 scoring formulas, fixed reference caps, weights, contribution
logic, filters, charts, and downloads remain unchanged.

This is a demonstration and decision-support tool. Its scores do not guarantee
affiliate revenue or profit.

## Application Modes

### Manual CSV

Manual mode preserves the complete Version 1.2 workflow. The uploaded CSV must
contain:

```text
product_name
platform
category
price
commission_rate
product_url
search_volume
search_growth_7d
social_mentions_7d
competitor_count
days_until_peak
seasonal_relevance
```

The six raw market signals are read by `ManualProvider`, labeled
`uploaded CSV`, and passed into the unchanged scoring pipeline.

### Mock Automatic Data

Automatic mode requires only:

```text
product_name
platform
category
price
commission_rate
product_url
```

The six raw-signal columns are optional. `MockProvider` generates deterministic
synthetic signals from the generated keywords.

Mock values are not real market data. They exist only to test the automatic
provider workflow and must not be treated as evidence of actual demand,
competition, seasonality, or profit potential.

## Keyword Generation

`keyword_generation.py` applies deterministic text rules:

1. Convert text to lowercase.
2. Replace punctuation with spaces.
3. Collapse repeated whitespace.
4. Remove duplicate phrases while preserving order.
5. Use `product_name` as the primary keyword.
6. Use `category` to enrich related keywords and search queries.

Example:

```text
primary_keyword:
ai resume builder

related_keywords:
ai resume builder
career software
ai resume builder career software

search_queries:
ai resume builder
best ai resume builder
ai resume builder reviews
ai resume builder career software
```

`platform` remains metadata for filtering, routing, or future provider
selection. It is not added to buyer-demand queries by default.

## Provider Architecture

```text
market_data/
├── base_provider.py
├── manual_provider.py
├── mock_provider.py
└── service.py
```

`base_provider.py` defines the shared provider interface, result model,
validation, and controlled error types for:

- missing credentials
- timeouts
- incomplete responses
- invalid values
- rate limits
- general provider failures

Every provider result contains:

```text
search_volume
search_growth_7d
social_mentions_7d
competitor_count
days_until_peak
seasonal_relevance
data_source
retrieved_at
confidence_level
retrieval_status
error_message
```

`service.py` processes products independently. One failed product never stops
the remaining products.

## Fallback Behavior

In automatic mode:

1. The provider is called for each product.
2. A complete, valid provider response is used when retrieval succeeds.
3. If retrieval fails, the app checks that product's optional CSV signals.
4. All six optional signals must be present and valid to serve as fallback.
5. Valid fallback values are labeled `fallback data`.
6. Without valid fallback, only that product is labeled `failed retrieval` and
   excluded from scoring.

Missing, incomplete, or invalid fallback fields do not reject the automatic
upload. They matter only if provider retrieval fails for that row.

## Data Sources And Status

The interface and ranked download show:

```text
data_source
retrieval_status
retrieved_at
confidence_level
error_message
```

Possible sources include:

```text
uploaded CSV
mock provider
fallback data
failed retrieval
```

## Caching

Provider objects are cached with Streamlit because they contain no uploaded
product data. Provider results are cached only in the current Streamlit user
session and keyed by normalized keyword requests.

Uploaded CSV rows and manual-provider results are not stored in a global
Streamlit data cache. Future API providers can extend the cache key with public
request parameters such as geography, language, date range, and provider name.

## Version 1.2 Scoring

The fixed reference values remain:

```text
maximum search volume: 100,000
maximum social mentions: 10,000
maximum competitor count: 100
growth range: -50% to +50%
maximum days until peak: 60
maximum commission per sale: $50
```

```text
commission_per_sale = price * commission_rate
commission_score = clip(commission_per_sale / 50 * 100, 0, 100)

trend_score maps:
-50% or lower = 0
0% = 50
+50% or higher = 100

demand_score =
  normalized_search_volume * 0.70
  + normalized_social_mentions * 0.30

competition_score =
  clip(competitor_count / 100 * 100, 0, 100)

competition_opportunity = 100 - competition_score

timing_urgency_score =
  clip(100 - days_until_peak / 60 * 100, 0, 100)

urgency_score =
  timing_urgency_score * 0.60
  + seasonal_relevance * 0.40
```

The final fixed weights remain:

```text
commission: 0.30
trend: 0.25
demand: 0.20
competition: 0.15
urgency: 0.10
```

Users cannot change the caps or weights.

## Adding A Real Provider Later

A future provider should:

1. Subclass `MarketDataProvider`.
2. Implement `retrieve(product, keywords)`.
3. Return a complete `MarketDataResult`.
4. Convert provider-specific failures into the controlled provider errors.
5. Register the provider in the application provider registry.
6. Keep credentials in Streamlit secrets rather than source code.

Possible future integrations include:

- Google Ads Keyword Planning for keyword volume and competition signals
- YouTube Data API for recent video and engagement signals

Those integrations are not included in Version 1.3A and may require credentials,
quotas, approval, or paid access.

## Local Setup

Python 3.12 is recommended for Streamlit Community Cloud compatibility.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
streamlit run app.py
```

## Run Tests

```bash
python -m unittest discover -s tests
```

## Repository Structure

```text
affiliate-product-ranker/
├── .gitignore
├── app.py
├── keyword_generation.py
├── scoring.py
├── signal_processing.py
├── validation.py
├── market_data/
│   ├── __init__.py
│   ├── base_provider.py
│   ├── manual_provider.py
│   ├── mock_provider.py
│   └── service.py
├── sample_products.csv
├── requirements.txt
├── README.md
└── tests/
    ├── test_v12.py
    └── test_v13.py
```

## Streamlit Community Cloud

```text
Repository: <your-github-username>/<your-repository-name>
Branch: main
Entrypoint file: app.py
Python version: 3.12
Secrets: none for Version 1.3A
```

The template path is relative to `app.py`, so downloads work locally and after
cloud deployment.
