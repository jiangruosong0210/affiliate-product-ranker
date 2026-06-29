# Affiliate Product Ranker MVP

## Project Overview

Affiliate Product Ranker Version 1.7 supports three independent decision layers:

1. Which products have the strongest short-term market opportunity?
2. For the same product, which platform-specific affiliate offer is most
   attractive?
3. Which promotional-video patterns and text signals have the strongest
   observed attention and engagement evidence?

The Product Opportunity Score from Versions 1.2 and 1.3A remains unchanged.
Version 1.4 added a separate Platform Offer Score. Version 1.5 adds Video
Insights without creating a video score. Version 1.6 adds rule-based video text
intelligence for optional titles, descriptions, transcripts, hashtags, creator
names, and language metadata. Version 1.7 adds local one-file MP4 upload
inspection for metadata, sampled frames, and lightweight visual heuristics.
These layers are not combined into a final profit prediction.

This is a rule-based demonstration and decision-support tool. It does not
guarantee affiliate revenue or profit.

Version 1.7 does not connect to platform APIs, scrape websites, download remote
videos, run external LLMs, perform speech-to-text, recognize products, identify
people, use OCR, generate videos, predict revenue, or publish content.

## Input Files

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

### Promotional Videos

`videos.csv` is optional:

```text
video_id
product_id
platform
title
video_url
publish_date
duration_seconds
views
likes
comments
shares
creator_followers
content_format
hook_type
demo_present
comparison_present
cta_present
main_feature
```

Version 1.6 adds optional text-enrichment fields:

```text
description
transcript
hashtags
creator_name
language
```

Existing Version 1.5 video CSV files remain valid without these columns. When
`language` is blank, the analysis value is `unknown`; the app does not silently
assume English.

Required video fields are `video_id`, `product_id`, `platform`,
`publish_date`, `duration_seconds`, `views`, `content_format`, and `hook_type`.

Optional interaction metrics remain unknown when blank. They are never replaced
with zero. `video_url` may be blank and is never fetched automatically.

`hashtags` is kept as one raw CSV text field for ease of upload. Internally, the
app derives a normalized semicolon-separated list such as
`resume; career; ai`.

Controlled platforms:

```text
YouTube, TikTok, Instagram, Facebook, Other
```

Controlled content formats:

```text
demo, review, comparison, unboxing, tutorial,
testimonial, lifestyle, listicle, other
```

Controlled hook types:

```text
result_first, problem_solution, question, surprising_fact,
discount_offer, general_introduction, other
```

Boolean fields accept `true/false`, `yes/no`, or `1/0`, case-insensitively.
Blank optional booleans remain unknown.

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

Video validation additionally checks:

- unique, non-empty `video_id`
- matching product relationship
- parseable publication date
- positive duration
- non-negative whole-number counts
- valid platform, format, hook, and boolean values

Invalid video rows are retained in a downloadable exclusion report.

Interaction counts greater than views and malformed nonblank video URLs produce
warnings rather than exclusions. Warning rows remain eligible for analysis and
are included in a separate downloadable warning report.

## Video Metrics

```text
engagement_rate =
  (likes + comments + shares) / views

like_rate = likes / views
comment_rate = comments / views
share_rate = shares / views
view_to_follower_ratio = views / creator_followers
```

Rules:

- Engagement requires all three interaction metrics and positive views.
- Individual rates require their own numerator and positive views.
- Zero views produce unavailable view-based rates.
- Zero followers produce an unavailable follower ratio.
- Missing metrics remain unavailable.
- Rates are stored as decimals and displayed as percentages.
- Group comparisons use medians to reduce outlier influence.

No Video Promotion Score, conversion prediction, revenue prediction, or
profitability score is created.

## Uploaded MP4 Processing

Version 1.7 can inspect one directly uploaded MP4 at a time inside the Video
Insights tab. Uploaded videos are processed locally in temporary storage and are
not saved permanently.

Limits:

```text
file type: MP4 only
maximum file size: 25 MB
minimum duration: 1 second
maximum duration: 60 seconds
maximum sampled frames: 12
target processing time: under 30 seconds when possible
```

Extracted metadata:

```text
original_filename
safe_filename
file_size_bytes
file_hash
duration_seconds
width
height
aspect_ratio
video_orientation
resolution_label
frame_rate
estimated_frame_count
video_codec
audio_track_present
creation_timestamp
processing_status
processing_notes
short_form_eligible
```

Frame sampling prioritizes opening frames near 0.5, 1.5, and 2.5 seconds,
middle frames near 25%, 50%, and 75%, and closing frames near the final 3 and
final 1 seconds. If fewer than 12 unique timestamps are available, deterministic
evenly spaced fallback timestamps are added.

Approximate visual heuristics:

```text
average_brightness
average_contrast
black_frame_count
duplicate_frame_count
estimated_scene_change_count
approximate_shot_frequency
opening_frame_activity
```

These visual outputs are simple sampled-frame heuristics. They are not semantic
video understanding and do not detect products, objects, faces, identities, or
text overlays.

Audio handling is intentionally limited to detecting whether an audio track is
present. Version 1.7 does not extract WAV files, calculate silence ratio,
estimate speech presence, or run speech-to-text.

Users may paste transcript text or upload a `.txt` transcript. That transcript
is processed through the existing Version 1.6 text-intelligence pipeline.

Product association is manual and auditable. If valid product data exists, the
user may select one product from a dropdown. If no product is selected or no
product data exists, the uploaded video is marked `unassigned`.

## Video Text Intelligence

Version 1.6 preserves original uploaded text fields and adds derived analysis
fields:

```text
combined_text
cleaned_text
analysis_text
hashtag_list
text_word_count
text_analysis_status
text_analysis_notes
```

Text preparation is transparent:

- lowercase is used for analysis only
- whitespace is trimmed and collapsed
- URLs are removed from analysis text
- useful hook punctuation such as `?`, `%`, `$`, and `!` is preserved
- extremely long analysis text is capped while the original transcript remains
  available
- short text, unsupported language, malformed hashtags, duplicate text, and
  truncation produce warnings rather than exclusions

Rule-based detectors create explainable fields for:

- `detected_content_format`
- `detected_hook_type`
- `detected_cta_present`
- `detected_main_features`

Each detected label includes evidence phrases, evidence source, confidence
labels such as `high`, `medium`, or `low`, and notes for ambiguity or conflict.
These confidence labels are explainable rule-strength labels, not probability
scores.

Feature extraction combines:

- category-specific dictionaries
- normalized unigrams, bigrams, and trigrams
- stopword removal
- generic marketing-word filtering
- simple synonym normalization
- deterministic TF-IDF-style discovery for feature suggestions only

TF-IDF discovery does not determine content format, hook type, CTA status, or
recommendation eligibility.

## Manual And Detected Labels

Version 1.6 compares:

```text
content_format vs detected_content_format
hook_type vs detected_hook_type
cta_present vs detected_cta_present
main_feature vs detected_main_features
```

Comparison statuses are:

```text
exact_match
partial_match
mismatch
manual_missing
detected_missing
not_comparable
```

The dashboard calls these metrics agreement, not accuracy, because manual
labels may not be perfect ground truth.

Label modes:

```text
Manual first, detected fallback
Manual labels only
Detected labels only
Compare only
```

The default is `Manual first, detected fallback`. Existing manual labels remain
unchanged. Detected labels fill only missing or unknown manual values and never
silently overwrite the original uploaded fields. If no text fields are
provided, Version 1.5 behavior remains unchanged.

## Video Recommendations

Product-level evidence requires:

```text
at least 5 valid product videos
at least 3 product videos with positive views
at least 2 valid observations per candidate
```

Category fallback requires:

```text
at least 10 valid category videos
at least 3 distinct products
at least 3 valid observations per candidate
```

Every recommendation reports:

- evidence level: product, category fallback, or insufficient
- supporting video count
- valid engagement-metric count
- median engagement used
- comparison baseline
- preferred format, hook, and duration band
- demo, comparison, and CTA guidance
- feature worth emphasizing
- a transparent evidence summary

Recommendations are deterministic rules based only on uploaded data.

## Dashboard Tabs

1. **Overview**: counts, provider status, top product, recommended offer, timing.
2. **Product Ranking**: existing ranking, filters, Top N, chart, and download.
3. **Platform Offer Comparison**: offer filters and side-by-side product offers.
4. **Video Insights**: uploaded MP4 inspection, filters, metrics, text
   coverage, automated detection, extracted features, manual-vs-detected
   agreement, group summaries, recommendations, and video downloads.
5. **Data Quality**: exclusions, warnings, reasons, and report downloads.
6. **Scalability**: row counts and processing-stage timing.
7. **Methodology**: formulas, evidence rules, limitations, and future work.

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
invalid_sample_videos.csv
```

The clean files contain no intentional validation errors. Invalid examples are
kept separately and include duplicates, orphans, bad rates, missing payout
values, invalid booleans, payout types, statuses, video relationships, and
controlled video values.

Video files:

```text
sample_videos.csv: 30 valid sample videos
large_sample_videos.csv: exactly 5,000 valid videos
invalid_sample_videos.csv: separate exclusions and warning-only examples
```

The sample and large video files include optional Version 1.6 text fields. The
validation logic still accepts older files that contain only the Version 1.5
video columns.

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

Tests cover Versions 1.2 through 1.7, including import safety, product-only
regression, product-plus-offer regression, full product/offer/video regression,
text detection, manual-vs-detected agreement, label fallback modes, MP4 upload
processing, synthetic video metadata/frame sampling, and the complete clean
1,000-product, 2,500-offer, and 5,000-video run.

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
├── video_insights.py
├── video_text_analysis.py
├── video_upload_processing.py
├── video_validation.py
├── validation.py
├── market_data/
├── sample_products.csv
├── sample_offers.csv
├── large_sample_products.csv
├── large_sample_offers.csv
├── invalid_sample_products.csv
├── invalid_sample_offers.csv
├── sample_videos.csv
├── large_sample_videos.csv
├── invalid_sample_videos.csv
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

Future versions may add real affiliate APIs, a database, or historical
machine-learning models. Version 1.7 does not process MP4 batches, scrape
platforms, download remote videos, run speech-to-text, call external LLMs,
recognize products, identify people, use OCR, generate scripts, generate
videos, predict conversion or revenue, or publish social-media content.
