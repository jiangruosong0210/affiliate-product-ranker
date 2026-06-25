import csv
import random
from pathlib import Path


RANDOM_SEED = 140
PROJECT_DIR = Path(__file__).resolve().parent

PRODUCT_COLUMNS = [
    "product_id",
    "product_name",
    "category",
    "product_type",
    "product_url",
    "reference_price",
    "reference_commission_rate",
    "search_volume",
    "search_growth_7d",
    "social_mentions_7d",
    "competitor_count",
    "days_until_peak",
    "seasonal_relevance",
]
OFFER_COLUMNS = [
    "offer_id",
    "product_id",
    "platform",
    "payout_type",
    "offer_price",
    "commission_rate",
    "fixed_commission_amount",
    "commission_per_lead",
    "cookie_duration_days",
    "recurring_commission",
    "affiliate_url",
    "offer_status",
]

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


def write_csv(path, rows, columns):
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main():
    clean_products, clean_offers = generate_clean_data()
    invalid_products, invalid_offers = generate_invalid_data()
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


if __name__ == "__main__":
    main()
