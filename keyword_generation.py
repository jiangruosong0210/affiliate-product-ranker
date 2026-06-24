import re


def normalize_text(value) -> str:
    text = "" if value is None else str(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def unique_phrases(phrases) -> list[str]:
    seen = set()
    result = []

    for phrase in phrases:
        normalized = normalize_text(phrase)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    return result


def generate_keywords(product) -> dict[str, object]:
    primary_keyword = normalize_text(product.get("product_name", ""))
    category = normalize_text(product.get("category", ""))

    related_keywords = unique_phrases(
        [
            primary_keyword,
            category,
            f"{primary_keyword} {category}",
        ]
    )
    search_queries = unique_phrases(
        [
            primary_keyword,
            f"best {primary_keyword}",
            f"{primary_keyword} reviews",
            f"{primary_keyword} {category}",
        ]
    )

    return {
        "primary_keyword": primary_keyword,
        "related_keywords": related_keywords,
        "search_queries": search_queries,
    }
