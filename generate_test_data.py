import csv
import random
from pathlib import Path

from schemas import (
    OFFER_COLUMNS,
    PRODUCT_CORE_COLUMNS,
    SIGNAL_COLUMNS,
    VIDEO_ALL_COLUMNS,
    VIDEO_COLUMNS,
    VIDEO_CONTENT_FORMATS,
    VIDEO_HOOK_TYPES,
    VIDEO_PLATFORMS,
)

RANDOM_SEED = 140
PROJECT_DIR = Path(__file__).resolve().parent

PRODUCT_COLUMNS = PRODUCT_CORE_COLUMNS + SIGNAL_COLUMNS

CATEGORIES = [
    "Career Software",
    "Summer Gadgets",
    "Personal Finance",
    "Creator Tools",
    "Home Office",
    "Education",
    "Fitness",
    "Travel",
    "Pet Care",
    "Beauty",
    "Gaming",
    "Productivity",
]
PRODUCT_TYPES = [
    "software",
    "subscription",
    "physical",
    "course",
    "service",
    "mobile_app",
    "membership",
    "digital_download",
]
PLATFORMS = [
    "Amazon Associates",
    "PartnerStack",
    "Impact",
    "ShareASale",
    "CJ Affiliate",
    "Awin",
    "Rakuten Advertising",
    "Direct Program",
]
COOKIE_DURATIONS = [0, 1, 7, 14, 30, 60, 90]
PAYOUT_TYPES = ["one_time", "recurring", "fixed_amount", "lead"]
STATUSES = ["active", "active", "active", "unknown", "inactive"]
VIDEO_FORMATS = VIDEO_CONTENT_FORMATS[:-1]
VIDEO_HOOKS = VIDEO_HOOK_TYPES[:-1]
VIDEO_FEATURES = [
    "ease of use",
    "price",
    "speed",
    "design",
    "durability",
    "automation",
    "portability",
    "customer support",
]
VIDEO_DESCRIPTIONS = [
    "Honest review with pros and cons plus a link in bio.",
    "Step by step tutorial showing the setup and main benefits.",
    "Quick demo and real example with a current price reminder.",
    "Top 5 tips and best tools for this category.",
]
VIDEO_TRANSCRIPTS = [
    "Today I'm showing how it works. Use code TEST for a small discount.",
    "Struggling with setup? Here is how to fix it in a simple walkthrough.",
    "I got better results after using the template and export options.",
    "This comparison explains the alternative and when it is worth it.",
]
VIDEO_HASHTAGS = [
    "#demo #review #affiliate",
    "tutorial, setup, tips",
    "#career #automation #template",
    "comparison | tools | discount",
]


def generate_clean_data(seed=RANDOM_SEED):
    randomizer = random.Random(seed)
    products = []
    offers = []

    for index in range(1, 1001):
        product_id = f"P{index:04d}"
        category = randomizer.choice(CATEGORIES)
        product_type = randomizer.choice(PRODUCT_TYPES)
        reference_price = round(randomizer.uniform(5, 500), 2)
        products.append(
            {
                "product_id": product_id,
                "product_name": f"Synthetic {category} Product {index}",
                "category": category,
                "product_type": product_type,
                "product_url": f"https://example.com/products/{product_id.lower()}",
                "reference_price": reference_price,
                "reference_commission_rate": round(
                    randomizer.uniform(0.01, 0.60), 4
                ),
                "search_volume": randomizer.randint(0, 150_000),
                "search_growth_7d": randomizer.randint(-70, 90),
                "social_mentions_7d": randomizer.randint(0, 15_000),
                "competitor_count": randomizer.randint(0, 160),
                "days_until_peak": randomizer.randint(0, 90),
                "seasonal_relevance": randomizer.randint(0, 100),
            }
        )

        offer_count = ((index - 1) % 4) + 1
        for offer_number in range(1, offer_count + 1):
            offer_id = f"O{len(offers) + 1:05d}"
            payout_type = PAYOUT_TYPES[(index + offer_number) % len(PAYOUT_TYPES)]
            offer_price = round(
                reference_price * randomizer.uniform(0.80, 1.20),
                2,
            )
            offer = {
                "offer_id": offer_id,
                "product_id": product_id,
                "platform": randomizer.choice(PLATFORMS),
                "payout_type": payout_type,
                "offer_price": "",
                "commission_rate": "",
                "fixed_commission_amount": "",
                "commission_per_lead": "",
                "cookie_duration_days": randomizer.choice(COOKIE_DURATIONS),
                "recurring_commission": payout_type == "recurring",
                "affiliate_url": f"https://example.com/offers/{offer_id.lower()}",
                "offer_status": randomizer.choice(STATUSES),
            }
            if payout_type in {"one_time", "recurring"}:
                offer["offer_price"] = offer_price
                offer["commission_rate"] = round(randomizer.uniform(0.01, 0.75), 4)
            elif payout_type == "fixed_amount":
                offer["fixed_commission_amount"] = round(
                    randomizer.uniform(1, 150),
                    2,
                )
            else:
                offer["commission_per_lead"] = round(
                    randomizer.uniform(0.50, 75),
                    2,
                )
            offers.append(offer)

    assert len(products) == 1000
    assert len(offers) == 2500
    return products, offers


def generate_invalid_data():
    products = [
        {
            "product_id": "BAD-P1",
            "product_name": "Duplicate Product A",
            "category": "Testing",
            "product_type": "software",
            "product_url": "",
            "reference_price": 20,
            "reference_commission_rate": 0.20,
            "search_volume": 1000,
            "search_growth_7d": 5,
            "social_mentions_7d": 100,
            "competitor_count": 10,
            "days_until_peak": 20,
            "seasonal_relevance": 50,
        },
        {
            "product_id": "BAD-P1",
            "product_name": "Duplicate Product B",
            "category": "Testing",
            "product_type": "service",
            "product_url": "",
            "reference_price": 30,
            "reference_commission_rate": 0.25,
            "search_volume": 1200,
            "search_growth_7d": 4,
            "social_mentions_7d": 120,
            "competitor_count": 12,
            "days_until_peak": 22,
            "seasonal_relevance": 55,
        },
        {
            "product_id": "",
            "product_name": "Missing ID Product",
            "category": "Testing",
            "product_type": "physical",
            "product_url": "",
            "reference_price": 15,
            "reference_commission_rate": 0.10,
            "search_volume": 800,
            "search_growth_7d": 0,
            "social_mentions_7d": 50,
            "competitor_count": 8,
            "days_until_peak": 30,
            "seasonal_relevance": 40,
        },
    ]
    offers = [
        invalid_offer("BAD-O1", "MISSING-PRODUCT", "one_time", commission_rate=0.2),
        invalid_offer("BAD-O2", "P0001", "one_time", commission_rate=0),
        invalid_offer("BAD-O3", "P0001", "fixed_amount", fixed_commission_amount=""),
        invalid_offer("BAD-O4", "P0001", "lead", commission_per_lead=""),
        invalid_offer("BAD-O5", "P0001", "recurring", recurring_commission=False),
        invalid_offer("BAD-O6", "P0001", "one_time", recurring_commission="maybe"),
        invalid_offer("BAD-O7", "P0001", "invalid_type"),
        invalid_offer("BAD-O8", "P0001", "lead", offer_status="expired"),
        invalid_offer("BAD-DUP", "P0001", "fixed_amount"),
        invalid_offer("BAD-DUP", "P0002", "fixed_amount"),
    ]
    return products, offers


def generate_clean_video_data(product_ids, seed=RANDOM_SEED):
    randomizer = random.Random(seed + 15)
    videos = []

    for product_index, product_id in enumerate(product_ids):
        for video_number in range(5):
            video_id = f"V{len(videos) + 1:06d}"
            views = randomizer.randint(0, 1_000_000)
            likes = randomizer.randint(0, views) if views else 0
            comments = randomizer.randint(0, max(views // 20, 0)) if views else 0
            shares = randomizer.randint(0, max(views // 10, 0)) if views else 0
            followers = randomizer.randint(0, 500_000)
            videos.append(
                {
                    "video_id": video_id,
                    "product_id": product_id,
                    "platform": randomizer.choice(VIDEO_PLATFORMS),
                    "title": f"Synthetic Product Video {product_index + 1}-{video_number + 1}",
                    "video_url": f"https://example.com/videos/{video_id.lower()}",
                    "publish_date": (
                        pd_timestamp(2025, 1, 1, product_index * 5 + video_number)
                    ),
                    "duration_seconds": randomizer.randint(6, 240),
                    "views": views,
                    "likes": likes if video_number != 1 else "",
                    "comments": comments if video_number != 1 else "",
                    "shares": shares if video_number != 1 else "",
                    "creator_followers": followers if video_number != 2 else "",
                    "content_format": randomizer.choice(VIDEO_FORMATS),
                    "hook_type": randomizer.choice(VIDEO_HOOKS),
                    "demo_present": randomizer.choice([True, False, ""]),
                    "comparison_present": randomizer.choice([True, False, ""]),
                    "cta_present": randomizer.choice([True, False, ""]),
                    "main_feature": randomizer.choice(VIDEO_FEATURES),
                    "description": randomizer.choice(VIDEO_DESCRIPTIONS),
                    "transcript": randomizer.choice(VIDEO_TRANSCRIPTS),
                    "hashtags": randomizer.choice(VIDEO_HASHTAGS),
                    "creator_name": f"Creator {product_index % 25 + 1}",
                    "language": randomizer.choice(["en", "en", "unknown"]),
                }
            )

    return videos


def generate_invalid_video_data():
    base = {
        "video_id": "BAD-V1",
        "product_id": "P0001",
        "platform": "YouTube",
        "title": "Invalid synthetic video",
        "video_url": "",
        "publish_date": "2026-01-01",
        "duration_seconds": 30,
        "views": 100,
        "likes": 10,
        "comments": 2,
        "shares": 1,
        "creator_followers": 1000,
        "content_format": "demo",
        "hook_type": "result_first",
        "demo_present": True,
        "comparison_present": False,
        "cta_present": True,
        "main_feature": "testing",
        "description": "Bad fixture row with a demo and link in bio.",
        "transcript": "This is a short transcript for validation testing.",
        "hashtags": "#testing #demo",
        "creator_name": "Fixture Creator",
        "language": "en",
    }
    rows = [
        {**base, "video_id": "DUP-V"},
        {**base, "video_id": "DUP-V", "product_id": "P0002"},
        {**base, "video_id": "BAD-ORPHAN", "product_id": "MISSING"},
        {**base, "video_id": "BAD-NEGATIVE", "views": -1},
        {**base, "video_id": "BAD-DURATION", "duration_seconds": 0},
        {**base, "video_id": "BAD-DATE", "publish_date": "not-a-date"},
        {**base, "video_id": "BAD-PLATFORM", "platform": "Unknown Network"},
        {**base, "video_id": "BAD-FORMAT", "content_format": "dance"},
        {**base, "video_id": "BAD-HOOK", "hook_type": "mystery"},
        {**base, "video_id": "BAD-BOOL", "demo_present": "maybe"},
        {
            **base,
            "video_id": "WARN-URL",
            "video_url": "example.com/video",
        },
        {
            **base,
            "video_id": "WARN-LIKES",
            "views": 10,
            "likes": 11,
        },
        {
            **base,
            "video_id": "WARN-TEXT",
            "transcript": "hola mundo",
            "hashtags": "#valid #%$",
            "language": "es",
        },
    ]
    return rows


def generate_sample_video_data():
    return generate_clean_video_data(
        ["P001", "P002", "P003", "P004", "P005", "P006"],
        seed=15,
    )


def pd_timestamp(year, month, day, offset_days):
    from datetime import date, timedelta

    return (date(year, month, day) + timedelta(days=offset_days)).isoformat()


def invalid_offer(
    offer_id,
    product_id,
    payout_type,
    commission_rate=0.2,
    fixed_commission_amount=20,
    commission_per_lead=10,
    recurring_commission=False,
    offer_status="active",
):
    return {
        "offer_id": offer_id,
        "product_id": product_id,
        "platform": "Synthetic Invalid Platform",
        "payout_type": payout_type,
        "offer_price": 100,
        "commission_rate": commission_rate,
        "fixed_commission_amount": fixed_commission_amount,
        "commission_per_lead": commission_per_lead,
        "cookie_duration_days": 30,
        "recurring_commission": recurring_commission,
        "affiliate_url": "",
        "offer_status": offer_status,
    }


def write_csv(path, rows, columns, lineterminator="\r\n"):
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=columns,
            lineterminator=lineterminator,
        )
        writer.writeheader()
        writer.writerows(rows)


def main():
    clean_products, clean_offers = generate_clean_data()
    invalid_products, invalid_offers = generate_invalid_data()
    clean_videos = generate_clean_video_data(
        [product["product_id"] for product in clean_products]
    )
    invalid_videos = generate_invalid_video_data()
    sample_videos = generate_sample_video_data()
    write_csv(PROJECT_DIR / "large_sample_products.csv", clean_products, PRODUCT_COLUMNS)
    write_csv(PROJECT_DIR / "large_sample_offers.csv", clean_offers, OFFER_COLUMNS)
    write_csv(
        PROJECT_DIR / "invalid_sample_products.csv",
        invalid_products,
        PRODUCT_COLUMNS,
    )
    write_csv(
        PROJECT_DIR / "invalid_sample_offers.csv",
        invalid_offers,
        OFFER_COLUMNS,
    )
    write_csv(
        PROJECT_DIR / "sample_videos.csv",
        sample_videos,
        VIDEO_ALL_COLUMNS,
        lineterminator="\n",
    )
    write_csv(
        PROJECT_DIR / "large_sample_videos.csv",
        clean_videos,
        VIDEO_ALL_COLUMNS,
        lineterminator="\n",
    )
    write_csv(
        PROJECT_DIR / "invalid_sample_videos.csv",
        invalid_videos,
        VIDEO_ALL_COLUMNS,
        lineterminator="\n",
    )


if __name__ == "__main__":
    main()
