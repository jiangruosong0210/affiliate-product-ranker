import math
import re
from collections import Counter, defaultdict

import pandas as pd


TEXT_COLUMNS = ["title", "description", "transcript", "hashtags"]
MAX_ANALYSIS_CHARS = 5000
SHORT_TEXT_WORD_LIMIT = 5
SUPPORTED_LANGUAGES = {"en", "english"}

FORMAT_PRIORITY = [
    "comparison",
    "review",
    "tutorial",
    "demo",
    "unboxing",
    "testimonial",
    "listicle",
    "lifestyle",
    "other",
]
HOOK_PRIORITY = [
    "discount_offer",
    "result_first",
    "problem_solution",
    "surprising_fact",
    "question",
    "general_introduction",
    "other",
]

FORMAT_RULES = {
    "demo": [
        "demo",
        "watch me use",
        "how it works",
        "show you how",
        "real example",
    ],
    "review": [
        "review",
        "honest review",
        "my thoughts",
        "pros and cons",
        "is it worth it",
    ],
    "comparison": [
        " vs ",
        " versus ",
        "compared to",
        "better than",
        "alternative to",
    ],
    "unboxing": [
        "unboxing",
        "first look",
        "what's inside",
        "whats inside",
        "just arrived",
    ],
    "tutorial": [
        "tutorial",
        "step by step",
        "how to",
        "walkthrough",
        "set up",
    ],
    "testimonial": [
        "my results",
        "before and after",
        "case study",
        "helped me",
        "i used this",
    ],
    "lifestyle": [
        "day in my life",
        "routine",
        "with me",
        "aesthetic",
        "setup tour",
    ],
    "listicle": [
        "top 5",
        "top five",
        "3 ways",
        "best tools",
        "things i wish",
    ],
}

HOOK_RULES = {
    "result_first": [
        "i got",
        "we increased",
        "saved me",
        "before and after",
        "% faster",
        "$ saved",
    ],
    "problem_solution": [
        "struggling with",
        "tired of",
        "the problem is",
        "here's how to fix",
        "heres how to fix",
    ],
    "question": [
        "why ",
        "how ",
        "what ",
        "should you",
    ],
    "surprising_fact": [
        "i didn't expect",
        "i didnt expect",
        "nobody tells you",
        "surprising",
        "secret",
        "hidden",
    ],
    "discount_offer": [
        "use code",
        "% off",
        "deal",
        "discount",
        "limited time",
        "sale",
    ],
    "general_introduction": [
        "today i'm showing",
        "today im showing",
        "this is",
        "let's talk about",
        "lets talk about",
        "introducing",
    ],
}

CTA_RULES = {
    "discount_code": ["use my code", "use code", "promo code"],
    "affiliate_link": [
        "link in bio",
        "check the link",
        "click below",
        "link in description",
    ],
    "purchase": ["shop now", "buy now", "get yours", "order today"],
    "price_check": ["check the current price", "see today's price"],
    "learn_more": ["learn more", "read more", "see details"],
}
CTA_PRIORITY = [
    "discount_code",
    "affiliate_link",
    "purchase",
    "price_check",
    "learn_more",
]
CTA_NEGATIONS = [
    "don't buy now",
    "dont buy now",
    "do not buy now",
    "no link",
    "not sponsored",
]

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "has",
    "have",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "our",
    "the",
    "this",
    "to",
    "use",
    "using",
    "was",
    "we",
    "with",
    "you",
    "your",
}
GENERIC_FEATURE_WORDS = {
    "amazing",
    "awesome",
    "best",
    "buy",
    "deal",
    "good",
    "great",
    "link",
    "now",
    "product",
    "really",
    "review",
    "shop",
    "stuff",
    "super",
    "thing",
    "today",
    "tutorial",
    "video",
}
SYNONYMS = {
    "templates": "template",
    "automation": "automation",
    "automated": "automation",
    "automate": "automation",
    "exports": "export",
    "exporting": "export",
    "pdfs": "pdf",
    "resumes": "resume",
}
CATEGORY_FEATURES = {
    "career software": [
        "resume template",
        "resume score",
        "cover letter",
        "job match",
        "export pdf",
        "ai suggestions",
    ],
    "creator tools": [
        "video editing",
        "caption generator",
        "content calendar",
        "analytics dashboard",
        "thumbnail maker",
    ],
    "home office": [
        "ergonomic design",
        "noise reduction",
        "cable management",
        "desk setup",
    ],
    "fitness": [
        "workout plan",
        "progress tracking",
        "meal plan",
        "heart rate",
    ],
    "personal finance": [
        "budget tracking",
        "cash back",
        "credit score",
        "expense alerts",
    ],
}


def enrich_video_text(videos_df):
    result = videos_df.copy()
    for column in ["description", "transcript", "hashtags", "creator_name", "language"]:
        if column not in result.columns:
            result[column] = ""

    prepared_rows = []
    cleaned_text_counts = Counter()
    for _, row in result.iterrows():
        prepared = prepare_text_row(row)
        prepared_rows.append(prepared)
        if prepared["cleaned_text"]:
            cleaned_text_counts[prepared["cleaned_text"]] += 1

    warnings = []
    enriched_values = []
    for index, prepared in zip(result.index, prepared_rows):
        row = result.loc[index]
        notes = list(prepared.pop("notes"))
        if prepared["cleaned_text"] and cleaned_text_counts[prepared["cleaned_text"]] > 1:
            notes.append("duplicate text")

        format_detection = detect_content_format(prepared, row)
        hook_detection = detect_hook_type(prepared)
        cta_detection = detect_cta(prepared)
        features = extract_features(prepared, row)

        enriched = {
            **prepared,
            **format_detection,
            **hook_detection,
            **cta_detection,
            **features,
            "text_analysis_notes": "; ".join(notes),
        }
        enriched_values.append(enriched)
        if notes:
            warning_record = row.to_dict()
            warning_record["warning_reasons"] = "; ".join(notes)
            warning_record["source_row"] = index + 2
            warnings.append(warning_record)

    enriched_df = pd.concat(
        [result.reset_index(drop=True), pd.DataFrame(enriched_values)],
        axis=1,
    )
    comparison_df = compare_manual_detected_labels(enriched_df)
    feature_summary = summarize_extracted_features(enriched_df)
    return enriched_df, pd.DataFrame(warnings), comparison_df, feature_summary


def prepare_text_row(row):
    notes = []
    raw_parts = []
    for column in TEXT_COLUMNS:
        value = normalize_original_text(row.get(column, ""))
        raw_parts.append(value)

    title, description, transcript, hashtags = raw_parts
    hashtag_list, hashtag_notes = normalize_hashtags(hashtags)
    notes.extend(hashtag_notes)

    combined_text = " ".join(part for part in raw_parts if part)
    cleaned_text = clean_for_analysis(
        " ".join([title, description, transcript, " ".join(hashtag_list)])
    )
    analysis_text = cleaned_text
    if len(analysis_text) > MAX_ANALYSIS_CHARS:
        analysis_text = analysis_text[:MAX_ANALYSIS_CHARS].rsplit(" ", 1)[0]
        notes.append("analysis text truncated")

    word_count = len(re.findall(r"\b[\w'-]+\b", cleaned_text))
    language = normalize_language(row.get("language", ""))
    status = "analyzed"
    if not cleaned_text:
        status = "no_text"
    elif language not in {"unknown", *SUPPORTED_LANGUAGES}:
        status = "unsupported_language"
        notes.append("unsupported language")
    elif word_count < SHORT_TEXT_WORD_LIMIT:
        status = "limited_text"
        notes.append("very short text")
    elif "analysis text truncated" in notes:
        status = "too_long_truncated"

    return {
        "combined_text": combined_text,
        "cleaned_text": cleaned_text,
        "analysis_text": analysis_text,
        "hashtag_list": "; ".join(hashtag_list),
        "text_word_count": word_count,
        "text_analysis_status": status,
        "normalized_language": language,
        "notes": notes,
    }


def detect_content_format(prepared, row):
    text_sources = source_texts(prepared, row)
    matches = defaultdict(list, collect_rule_matches(FORMAT_RULES, text_sources))
    matched_labels = set(matches)
    title = text_sources["title"]
    title_listicle = re.search(r"(^|\b)(top|best)\s+\d+\b|\b\d+\s+(ways|tips|tools)\b", title)
    if title_listicle:
        matches["listicle"].append({"phrase": title_listicle.group(0), "source": "title"})
        matched_labels.add("listicle")

    if not prepared["analysis_text"]:
        value = "unknown"
        confidence = "unknown"
        evidence = ""
        source = ""
        notes = "insufficient text"
    elif not matches:
        value = "other"
        confidence = "low"
        evidence = ""
        source = ""
        notes = "no clear format pattern"
    else:
        value = choose_by_priority(matches, FORMAT_PRIORITY)
        selected = matches[value][0]
        evidence = selected["phrase"]
        source = selected["source"]
        confidence = confidence_for(matches[value], source)
        notes = (
            "ambiguous format evidence"
            if len([label for label in matches if label != value]) > 0
            else ""
        )
    return {
        "detected_content_format": value,
        "detected_content_format_evidence": evidence,
        "detected_content_format_source": source,
        "detected_content_format_confidence": confidence,
        "detected_content_format_notes": notes,
        "detected_content_format_all_evidence": serialize_matches(matches),
    }


def detect_hook_type(prepared):
    opening = opening_text(prepared)
    matches = defaultdict(list, collect_rule_matches(HOOK_RULES, {"opening": opening}))
    if "?" in opening:
        matches["question"].append({"phrase": "?", "source": "opening"})
    if re.match(r"^(why|how|what|should you)\b", opening):
        matches["question"].append(
            {"phrase": opening.split(" ", 1)[0], "source": "opening"}
        )

    if not opening:
        value = "unknown"
        confidence = "unknown"
        evidence = ""
        source = ""
        notes = "insufficient opening text"
    elif not matches:
        value = "other"
        confidence = "low"
        evidence = ""
        source = ""
        notes = "no clear hook pattern"
    else:
        value = choose_by_priority(matches, HOOK_PRIORITY)
        selected = matches[value][0]
        evidence = selected["phrase"]
        source = selected["source"]
        confidence = confidence_for(matches[value], source)
        notes = (
            "ambiguous hook evidence"
            if len([label for label in matches if label != value]) > 0
            else ""
        )
    return {
        "detected_hook_type": value,
        "detected_hook_phrase": evidence,
        "detected_hook_source": source,
        "detected_hook_confidence": confidence,
        "detected_hook_notes": notes,
        "detected_hook_all_evidence": serialize_matches(matches),
    }


def detect_cta(prepared):
    text = prepared["analysis_text"]
    negated = [phrase for phrase in CTA_NEGATIONS if phrase in text]
    matches = defaultdict(list, collect_rule_matches(CTA_RULES, {"analysis_text": text}))
    for cta_type in list(matches):
        matches[cta_type] = [
            match for match in matches[cta_type]
            if not is_negated_cta(match["phrase"], text)
        ]
        if not matches[cta_type]:
            del matches[cta_type]

    if not text:
        present = pd.NA
        phrase = ""
        cta_type = "unknown"
        source = ""
        confidence = "unknown"
        notes = "insufficient text"
    elif not matches:
        present = False
        phrase = ""
        cta_type = "none"
        source = ""
        confidence = "medium" if negated else "low"
        notes = "negated CTA phrase ignored" if negated else ""
    else:
        cta_type = choose_by_priority(matches, CTA_PRIORITY)
        selected = matches[cta_type][0]
        present = True
        phrase = selected["phrase"]
        source = selected["source"]
        confidence = confidence_for(matches[cta_type], source)
        notes = (
            "multiple CTA types detected"
            if len([label for label in matches if label != cta_type]) > 0
            else ""
        )
    return {
        "detected_cta_present": present,
        "detected_cta_phrase": phrase,
        "detected_cta_type": cta_type,
        "detected_cta_source": source,
        "detected_cta_confidence": confidence,
        "detected_cta_notes": notes,
        "detected_cta_all_evidence": serialize_matches(matches),
    }


def extract_features(prepared, row):
    text = prepared["analysis_text"]
    category = normalize_phrase(row.get("category", ""))
    dictionary_hits = []
    for feature in CATEGORY_FEATURES.get(category, []):
        if feature in text:
            dictionary_hits.append(feature)

    tokens = [
        normalize_token(token)
        for token in re.findall(r"\b[a-z][a-z0-9'-]*\b", text)
    ]
    tokens = [
        token for token in tokens
        if token and token not in STOPWORDS and token not in GENERIC_FEATURE_WORDS
    ]
    ngrams = build_ngrams(tokens)
    candidates = [
        gram for gram in ngrams
        if is_feature_candidate(gram)
    ]
    counts = Counter(candidates)
    tfidf_terms = deterministic_tfidf_terms(counts)

    ordered = []
    for item in dictionary_hits + tfidf_terms:
        normalized = normalize_phrase(item)
        if normalized and normalized not in ordered:
            ordered.append(normalized)
    selected = ordered[:5]
    return {
        "detected_main_features": "; ".join(selected),
        "detected_feature_count": len(selected),
        "feature_evidence_phrases": "; ".join(selected),
        "feature_extraction_method": (
            "dictionary + ngram frequency + deterministic tf-idf"
            if selected
            else "no feature evidence"
        ),
    }


def compare_manual_detected_labels(enriched_df):
    rows = []
    for _, row in enriched_df.iterrows():
        rows.append(
            {
                "video_id": row.get("video_id", ""),
                "product_id": row.get("product_id", ""),
                "content_format_agreement": compare_single_label(
                    row.get("content_format"),
                    row.get("detected_content_format"),
                ),
                "hook_type_agreement": compare_single_label(
                    row.get("hook_type"),
                    row.get("detected_hook_type"),
                ),
                "cta_present_agreement": compare_boolean_label(
                    row.get("cta_present"),
                    row.get("detected_cta_present"),
                ),
                "main_feature_agreement": compare_feature_label(
                    row.get("main_feature"),
                    row.get("detected_main_features"),
                ),
            }
        )
    return pd.DataFrame(rows)


def apply_label_precedence(enriched_df, mode):
    result = enriched_df.copy()
    result["effective_content_format"] = result.apply(
        lambda row: choose_label(
            row.get("content_format"),
            row.get("detected_content_format"),
            mode,
            unknown_values={"unknown"},
        ),
        axis=1,
    )
    result["effective_hook_type"] = result.apply(
        lambda row: choose_label(
            row.get("hook_type"),
            row.get("detected_hook_type"),
            mode,
            unknown_values={"unknown"},
        ),
        axis=1,
    )
    result["effective_cta_present"] = result.apply(
        lambda row: choose_label(
            row.get("cta_present"),
            row.get("detected_cta_present"),
            mode,
            unknown_values={"unknown", "none"},
        ),
        axis=1,
    )
    result["effective_main_features"] = result.apply(
        lambda row: choose_label(
            row.get("main_feature"),
            row.get("detected_main_features"),
            mode,
            unknown_values={"unknown"},
        ),
        axis=1,
    )
    result["label_source"] = result.apply(
        lambda row: label_source(row, mode),
        axis=1,
    )
    result["analysis_content_format"] = result["content_format"]
    result["analysis_hook_type"] = result["hook_type"]
    result["analysis_cta_present"] = result["cta_present"]
    result["analysis_main_feature"] = result["main_feature"]
    if mode != "Compare only":
        result["content_format"] = result["effective_content_format"]
        result["hook_type"] = result["effective_hook_type"]
        result["cta_present"] = result["effective_cta_present"]
        result["main_feature"] = result["effective_main_features"].apply(
            first_feature
        )
    return result


def summarize_extracted_features(enriched_df):
    rows = []
    counts = Counter()
    for features in enriched_df.get("detected_main_features", []):
        for feature in split_features(features):
            counts[feature] += 1
    for feature, count in counts.most_common():
        rows.append({"feature": feature, "video_count": count})
    return pd.DataFrame(rows)


def normalize_original_text(value):
    if pd.isna(value):
        return ""
    return " ".join(str(value).strip().split())


def normalize_language(value):
    text = normalize_original_text(value).lower()
    return text if text else "unknown"


def normalize_hashtags(value):
    text = normalize_original_text(value)
    if not text:
        return [], []
    raw_tokens = re.split(r"[,|;\s]+", text)
    tags = []
    notes = []
    for token in raw_tokens:
        if not token:
            continue
        cleaned = token.strip().lstrip("#").lower()
        cleaned = re.sub(r"[^a-z0-9_-]", "", cleaned)
        if not cleaned:
            notes.append("malformed hashtag")
            continue
        if cleaned not in tags:
            tags.append(cleaned)
    return tags, notes


def clean_for_analysis(text):
    text = text.lower()
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    text = re.sub(r"[^a-z0-9\s?!%$#'-]", " ", text)
    return " ".join(text.split())


def source_texts(prepared, row):
    return {
        "title": clean_for_analysis(row.get("title", "")),
        "description": clean_for_analysis(row.get("description", "")),
        "transcript": clean_for_analysis(row.get("transcript", "")),
        "hashtags": prepared["hashtag_list"].replace(";", " "),
        "analysis_text": prepared["analysis_text"],
    }


def opening_text(prepared):
    text = prepared["analysis_text"]
    if not text:
        return ""
    return text[:500]


def collect_rule_matches(rules, text_sources):
    matches = defaultdict(list)
    for label, phrases in rules.items():
        for source, text in text_sources.items():
            padded_text = f" {text} "
            for phrase in phrases:
                needle = phrase.lower()
                if needle in padded_text:
                    matches[label].append(
                        {"phrase": phrase.strip(), "source": source}
                    )
    return dict(matches)


def choose_by_priority(matches, priority):
    for label in priority:
        if label in matches:
            return label
    return next(iter(matches))


def confidence_for(matches, source):
    if source == "title" or len(matches) >= 2:
        return "high"
    return "medium"


def serialize_matches(matches):
    parts = []
    for label, label_matches in matches.items():
        phrases = ", ".join(
            f"{match['phrase']} ({match['source']})"
            for match in label_matches
        )
        parts.append(f"{label}: {phrases}")
    return "; ".join(parts)


def is_negated_cta(phrase, text):
    window_pattern = rf"(don't|dont|do not|no|not)\s+\w*\s*{re.escape(phrase)}"
    return bool(re.search(window_pattern, text))


def normalize_token(token):
    token = token.strip("'").lower()
    return SYNONYMS.get(token, token)


def normalize_phrase(value):
    if pd.isna(value):
        return ""
    tokens = [
        normalize_token(token)
        for token in re.findall(r"\b[a-z0-9'-]+\b", str(value).lower())
    ]
    return " ".join(token for token in tokens if token)


def build_ngrams(tokens):
    grams = []
    for size in [1, 2, 3]:
        for index in range(0, len(tokens) - size + 1):
            grams.append(" ".join(tokens[index:index + size]))
    return grams


def is_feature_candidate(phrase):
    tokens = phrase.split()
    if not tokens:
        return False
    if any(token in GENERIC_FEATURE_WORDS or token in STOPWORDS for token in tokens):
        return False
    return any(len(token) > 3 for token in tokens)


def deterministic_tfidf_terms(counts):
    if not counts:
        return []
    total = sum(counts.values())
    scored = []
    for phrase, count in counts.items():
        length_boost = 1 + (len(phrase.split()) - 1) * 0.2
        score = (count / total) * math.log(1 + total / count) * length_boost
        scored.append((score, count, phrase))
    scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return [phrase for _, _, phrase in scored[:5]]


def compare_single_label(manual, detected):
    manual_text = normalize_phrase(manual)
    detected_text = normalize_phrase(detected)
    if not manual_text:
        return "manual_missing"
    if not detected_text or detected_text == "unknown":
        return "detected_missing"
    return "exact_match" if manual_text == detected_text else "mismatch"


def compare_boolean_label(manual, detected):
    if pd.isna(manual):
        return "manual_missing"
    if pd.isna(detected) or detected == "unknown":
        return "detected_missing"
    return "exact_match" if bool(manual) is bool(detected) else "mismatch"


def compare_feature_label(manual, detected):
    manual_text = normalize_phrase(manual)
    detected_features = split_features(detected)
    if not manual_text:
        return "manual_missing"
    if not detected_features:
        return "detected_missing"
    if manual_text in detected_features:
        return "exact_match"
    manual_tokens = set(manual_text.split())
    for feature in detected_features:
        feature_tokens = set(feature.split())
        if manual_tokens & feature_tokens:
            return "partial_match"
    return "mismatch"


def split_features(value):
    if pd.isna(value) or not str(value).strip():
        return []
    return [
        normalize_phrase(part)
        for part in str(value).split(";")
        if normalize_phrase(part)
    ]


def choose_label(manual, detected, mode, unknown_values=None):
    unknown_values = unknown_values or set()
    if mode == "Manual labels only" or mode == "Compare only":
        return manual
    if mode == "Detected labels only":
        return detected if not is_missing_label(detected, unknown_values) else manual
    if not is_missing_label(manual, unknown_values):
        return manual
    return detected if not is_missing_label(detected, unknown_values) else manual


def label_source(row, mode):
    if mode == "Compare only":
        return "compare_only"
    if mode == "Manual labels only":
        return "manual"
    if mode == "Detected labels only":
        return "detected"
    detected_used = (
        is_missing_label(row.get("content_format"), {"unknown"})
        and not is_missing_label(row.get("detected_content_format"), {"unknown"})
    ) or (
        pd.isna(row.get("cta_present"))
        and not pd.isna(row.get("detected_cta_present"))
    ) or (
        is_missing_label(row.get("main_feature"), {"unknown"})
        and not is_missing_label(row.get("detected_main_features"), {"unknown"})
    )
    return "manual_with_detected_fallback" if detected_used else "manual"


def is_missing_label(value, unknown_values=None):
    unknown_values = unknown_values or set()
    if pd.isna(value):
        return True
    text = str(value).strip().lower()
    return text == "" or text in unknown_values


def first_feature(value):
    features = split_features(value)
    return features[0] if features else ""
