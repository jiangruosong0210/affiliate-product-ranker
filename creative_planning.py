import io
import json
import re
import zipfile
from copy import deepcopy
from datetime import datetime, timezone

import pandas as pd


DEFAULT_DISCLOSURE = "This content may contain affiliate links."

PLATFORM_PRESETS = {
    "TikTok": {
        "aspect_ratio": "9:16",
        "duration_seconds": 20,
        "pacing": "fast",
        "hook_timing": "first 2 seconds",
        "cta_timing": "final 3 seconds",
        "scene_count": 4,
    },
    "YouTube Shorts": {
        "aspect_ratio": "9:16",
        "duration_seconds": 30,
        "pacing": "quick but clear",
        "hook_timing": "first 3 seconds",
        "cta_timing": "final 4 seconds",
        "scene_count": 5,
    },
    "Instagram Reels": {
        "aspect_ratio": "9:16",
        "duration_seconds": 30,
        "pacing": "visual and concise",
        "hook_timing": "first 3 seconds",
        "cta_timing": "final 4 seconds",
        "scene_count": 5,
    },
    "Facebook Reels": {
        "aspect_ratio": "9:16",
        "duration_seconds": 30,
        "pacing": "clear and benefit-led",
        "hook_timing": "first 3 seconds",
        "cta_timing": "final 5 seconds",
        "scene_count": 5,
    },
    "Other": {
        "aspect_ratio": "9:16",
        "duration_seconds": 30,
        "pacing": "balanced",
        "hook_timing": "first 3 seconds",
        "cta_timing": "final 5 seconds",
        "scene_count": 5,
    },
}

CAMPAIGN_OBJECTIVES = {
    "awareness": {
        "template": "product demo",
        "cta": "Learn more before you decide.",
        "emphasis": "introduce the product clearly",
    },
    "engagement": {
        "template": "review",
        "cta": "Share what you would compare it with.",
        "emphasis": "invite lightweight interaction",
    },
    "product education": {
        "template": "tutorial",
        "cta": "Check the details if this fits your workflow.",
        "emphasis": "explain how the product helps",
    },
    "product comparison": {
        "template": "comparison",
        "cta": "Compare the options before choosing.",
        "emphasis": "frame tradeoffs without claiming a winner",
    },
    "offer promotion": {
        "template": "offer promotion",
        "cta": "Check the current offer details.",
        "emphasis": "mention only verified offer details",
    },
    "click-through": {
        "template": "problem-solution",
        "cta": "Open the link to review the details.",
        "emphasis": "make the next click feel useful",
    },
    "conversion-oriented promotion": {
        "template": "problem-solution",
        "cta": "Review the product and offer details before deciding.",
        "emphasis": "strengthen structure and CTA clarity without predicting conversion",
    },
}

ALLOWED_DURATIONS = [15, 20, 30, 45, 60]
DURATION_SCENE_COUNTS = {15: 3, 20: 4, 30: 5, 45: 6, 60: 8}
CONTENT_TEMPLATES = [
    "product demo",
    "comparison",
    "review",
    "tutorial",
    "problem-solution",
    "result-first",
    "offer promotion",
]
UNSUPPORTED_CLAIMS = [
    "guaranteed results",
    "best product",
    "works instantly",
    "clinically proven",
    "number-one product",
    "specific savings",
    "performance improvements",
    "health claims",
    "safety claims",
]
UNSUPPORTED_CLAIM_PATTERNS = [
    re.compile(r"\bguarantee(?:d|s)?\b", re.IGNORECASE),
    re.compile(r"\bbest\b", re.IGNORECASE),
    re.compile(r"\bworks instantly\b", re.IGNORECASE),
    re.compile(r"\bclinically proven\b", re.IGNORECASE),
    re.compile(r"\bnumber[- ]?one\b", re.IGNORECASE),
    re.compile(r"\bsave\s+\$?\d+", re.IGNORECASE),
    re.compile(r"\bimprove(?:s|d)?\s+by\s+\d+%?", re.IGNORECASE),
    re.compile(r"\bcure|treat|diagnose|prevent\b", re.IGNORECASE),
    re.compile(r"\bsafe for everyone\b", re.IGNORECASE),
]


def normalize_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def row_to_dict(row):
    if row is None:
        return {}
    if hasattr(row, "to_dict"):
        return row.to_dict()
    return dict(row)


def product_label(product):
    return normalize_text(product.get("product_name")) or "the product"


def clean_feature_list(value):
    if isinstance(value, list):
        parts = value
    else:
        parts = re.split(r"[,;\n]", normalize_text(value))
    cleaned = []
    seen = set()
    for part in parts:
        text = " ".join(str(part).strip().split())
        if text and text.lower() not in seen:
            cleaned.append(text)
            seen.add(text.lower())
    return cleaned


def select_video_evidence(video_recommendation):
    video_recommendation = row_to_dict(video_recommendation)
    evidence_level = normalize_text(video_recommendation.get("evidence_level"))
    if evidence_level in {"product-level evidence", "category-level fallback"}:
        return {
            "evidence_level": evidence_level,
            "source": (
                "product-level video recommendation"
                if evidence_level == "product-level evidence"
                else "category-level video recommendation"
            ),
            "recommendation": video_recommendation,
            "warning": "",
        }
    return {
        "evidence_level": "deterministic default",
        "source": "deterministic default template",
        "recommendation": video_recommendation,
        "warning": "Insufficient video evidence; a deterministic default template was used.",
    }


def select_offer(offer):
    offer = row_to_dict(offer)
    if not offer:
        return {}, ""
    status = normalize_text(offer.get("offer_status")).lower()
    if status == "inactive":
        return {}, "Inactive offers are excluded from promotion planning."
    if status == "unknown":
        return offer, "Offer availability is unknown; verify terms before using it."
    return offer, ""


def choose_template(settings, evidence):
    override = normalize_text(settings.get("template_override"))
    if override and override != "Auto":
        return override
    recommendation = evidence.get("recommendation", {})
    content_format = normalize_text(recommendation.get("preferred_content_format"))
    format_map = {
        "demo": "product demo",
        "comparison": "comparison",
        "review": "review",
        "tutorial": "tutorial",
        "testimonial": "review",
        "listicle": "comparison",
    }
    if evidence["evidence_level"] != "deterministic default":
        mapped = format_map.get(content_format)
        if mapped:
            return mapped
    objective = normalize_text(settings.get("campaign_objective"))
    return CAMPAIGN_OBJECTIVES.get(
        objective,
        CAMPAIGN_OBJECTIVES["awareness"],
    )["template"]


def choose_hook(settings, evidence, product):
    override = normalize_text(settings.get("hook_type_override"))
    if override and override != "Auto":
        return override.replace("_", " ")
    recommendation = evidence.get("recommendation", {})
    hook = normalize_text(recommendation.get("preferred_hook_type"))
    if evidence["evidence_level"] != "deterministic default" and hook:
        return hook.replace("_", " ")
    objective = normalize_text(settings.get("campaign_objective"))
    if objective in {"click-through", "conversion-oriented promotion"}:
        return "problem solution"
    if objective == "product comparison":
        return "comparison"
    return f"clear reason to consider {product_label(product)}"


def build_creative_context(product, offer=None, video_recommendation=None, settings=None):
    settings = settings or {}
    product = row_to_dict(product)
    selected_offer, offer_warning = select_offer(offer)
    evidence = select_video_evidence(video_recommendation)
    objective = normalize_text(settings.get("campaign_objective")) or "awareness"
    objective_config = CAMPAIGN_OBJECTIVES.get(
        objective,
        CAMPAIGN_OBJECTIVES["awareness"],
    )
    platform = normalize_text(settings.get("target_platform")) or "TikTok"
    preset = deepcopy(PLATFORM_PRESETS.get(platform, PLATFORM_PRESETS["Other"]))
    duration = int(settings.get("duration_seconds") or preset["duration_seconds"])
    if duration not in ALLOWED_DURATIONS:
        duration = preset["duration_seconds"]
    aspect_ratio = normalize_text(settings.get("aspect_ratio")) or preset["aspect_ratio"]

    recommendation = evidence.get("recommendation", {})
    feature_source = "user override"
    features = clean_feature_list(settings.get("key_product_features"))
    if not features:
        feature_source = "video recommendation"
        features = clean_feature_list(recommendation.get("feature_to_emphasize"))
    if not features:
        feature_source = "product/category fallback"
        features = clean_feature_list(product.get("category"))

    disclosure_text = normalize_text(settings.get("disclosure_text")) or DEFAULT_DISCLOSURE
    warnings = []
    if evidence["warning"]:
        warnings.append(evidence["warning"])
    if offer_warning:
        warnings.append(offer_warning)
    if feature_source == "product/category fallback":
        warnings.append(
            "Limited product detail was available; feature claims are intentionally broad."
        )
    if objective == "conversion-oriented promotion":
        warnings.append(
            "Conversion-oriented promotion changes structure and CTA emphasis; it does not predict conversion performance."
        )

    return {
        "product": product,
        "offer": selected_offer,
        "video_evidence": evidence,
        "settings": {
            "target_platform": platform,
            "campaign_objective": objective,
            "duration_seconds": duration,
            "aspect_ratio": aspect_ratio,
            "tone": normalize_text(settings.get("tone")) or "clear and helpful",
            "target_audience": normalize_text(settings.get("target_audience")) or "interested buyers",
            "cta": normalize_text(settings.get("cta")) or objective_config["cta"],
            "brand_constraints": normalize_text(settings.get("brand_constraints")),
            "product_notes": normalize_text(settings.get("product_notes")),
            "include_disclosure": bool(settings.get("include_disclosure", True)),
            "disclosure_text": disclosure_text,
            "pacing": normalize_text(settings.get("pacing")) or preset["pacing"],
            "hook_timing": normalize_text(settings.get("hook_timing")) or preset["hook_timing"],
            "cta_timing": normalize_text(settings.get("cta_timing")) or preset["cta_timing"],
        },
        "creative_choices": {
            "template": choose_template(settings, evidence),
            "hook_type": choose_hook(settings, evidence, product),
            "features": features,
            "feature_source": feature_source,
            "objective_emphasis": objective_config["emphasis"],
        },
        "warnings": warnings,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def build_video_brief(context):
    product = context["product"]
    offer = context["offer"]
    settings = context["settings"]
    choices = context["creative_choices"]
    product_name = product_label(product)
    category = normalize_text(product.get("category")) or "the category"
    offer_detail = ""
    if offer:
        platform = normalize_text(offer.get("platform"))
        offer_price = offer.get("offer_price")
        if platform:
            offer_detail = f"Use the active offer on {platform}."
        if pd.notna(offer_price) and str(offer_price).strip():
            offer_detail += f" Current uploaded offer price: {offer_price}."

    return {
        "product_id": normalize_text(product.get("product_id")),
        "product_name": product_name,
        "category": category,
        "target_platform": settings["target_platform"],
        "campaign_objective": settings["campaign_objective"],
        "duration_seconds": settings["duration_seconds"],
        "aspect_ratio": settings["aspect_ratio"],
        "tone": settings["tone"],
        "target_audience": settings["target_audience"],
        "selected_template": choices["template"],
        "hook_type": choices["hook_type"],
        "pacing": settings["pacing"],
        "key_product_features": choices["features"],
        "feature_source": choices["feature_source"],
        "recommended_cta": settings["cta"],
        "disclosure_text": (
            settings["disclosure_text"] if settings["include_disclosure"] else ""
        ),
        "source_evidence": context["video_evidence"]["source"],
        "evidence_level": context["video_evidence"]["evidence_level"],
        "offer_guidance": offer_detail,
        "product_notes": settings["product_notes"],
        "brand_constraints": settings["brand_constraints"],
        "warnings": context["warnings"],
    }


def scene_timings(duration_seconds):
    scene_count = DURATION_SCENE_COUNTS[int(duration_seconds)]
    base = duration_seconds // scene_count
    remainder = duration_seconds % scene_count
    timings = []
    current = 0
    for index in range(scene_count):
        length = base + (1 if index < remainder else 0)
        start = current
        end = current + length
        timings.append((start, end))
        current = end
    timings[-1] = (timings[-1][0], duration_seconds)
    return timings


def scene_purpose(index, total, template, objective):
    if index == 0:
        return "hook"
    if index == total - 1:
        return "CTA and disclosure"
    if template == "comparison":
        return "comparison point"
    if template == "tutorial":
        return "step or workflow"
    if template == "offer promotion":
        return "verified offer context"
    if template == "problem-solution":
        return "problem and product fit"
    if objective == "engagement":
        return "discussion prompt"
    return "product value"


def build_scene_line(brief, index, total):
    product_name = brief["product_name"]
    feature = (
        brief["key_product_features"][index % len(brief["key_product_features"])]
        if brief["key_product_features"]
        else brief["category"]
    )
    if index == 0:
        return {
            "voice_over": (
                f"If you are comparing options for {brief['category']}, "
                f"here is where {product_name} may fit."
            ),
            "on_screen_text": f"{product_name}: quick look",
            "visual": f"Open with {product_name} in a clean, real-use context.",
        }
    if index == total - 1:
        disclosure = brief["disclosure_text"]
        voice = brief["recommended_cta"]
        if disclosure:
            voice = f"{voice} {disclosure}"
        return {
            "voice_over": voice,
            "on_screen_text": brief["recommended_cta"],
            "visual": "End on a simple product screen and clear next step.",
        }
    return {
        "voice_over": f"Focus on {feature} and show how it helps the audience evaluate the product.",
        "on_screen_text": feature,
        "visual": f"Show {feature} with straightforward product footage or UI context.",
    }


def build_storyboard(brief):
    timings = scene_timings(brief["duration_seconds"])
    total = len(timings)
    rows = []
    for index, (start, end) in enumerate(timings):
        line = build_scene_line(brief, index, total)
        purpose = scene_purpose(
            index,
            total,
            brief["selected_template"],
            brief["campaign_objective"],
        )
        rows.append(
            {
                "scene_number": index + 1,
                "start_time": start,
                "end_time": end,
                "scene_purpose": purpose,
                "visual_description": line["visual"],
                "camera_or_framing": "Vertical close-up or screen capture" if brief["aspect_ratio"] == "9:16" else "Clean product-focused framing",
                "product_action": "Show only uploaded product facts and user-provided notes.",
                "voice_over": line["voice_over"],
                "on_screen_text": line["on_screen_text"],
                "transition": "Quick cut" if index < total - 1 else "End card",
                "audio_or_music_guidance": f"{brief['tone']} background music, no distracting lyrics",
                "CTA placement": "yes" if index == total - 1 else "no",
                "source evidence": brief["source_evidence"],
            }
        )
    return rows


def build_script(brief, storyboard):
    lines = [
        f"Video script for {brief['product_name']}",
        f"Platform: {brief['target_platform']} | Duration: {brief['duration_seconds']} seconds | Aspect ratio: {brief['aspect_ratio']}",
        "",
    ]
    for scene in storyboard:
        lines.extend(
            [
                f"{scene['start_time']:02d}-{scene['end_time']:02d}s | Scene {scene['scene_number']}: {scene['scene_purpose']}",
                f"Voice-over: {scene['voice_over']}",
                f"On-screen text: {scene['on_screen_text']}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def build_generation_prompts(brief, storyboard):
    scene_prompt = " ".join(
        f"Scene {scene['scene_number']} ({scene['start_time']}-{scene['end_time']}s): {scene['visual_description']} On-screen text: {scene['on_screen_text']}."
        for scene in storyboard
    )
    concise = (
        f"Create a {brief['duration_seconds']}-second {brief['aspect_ratio']} "
        f"{brief['target_platform']} video for {brief['product_name']} using a "
        f"{brief['selected_template']} structure, {brief['tone']} tone, and a "
        f"clear CTA: {brief['recommended_cta']}"
    )
    detailed = (
        f"Product: {brief['product_name']}. Category: {brief['category']}. "
        f"Audience: {brief['target_audience']}. Objective: {brief['campaign_objective']}. "
        f"Pacing: {brief['pacing']}. Evidence: {brief['source_evidence']}. "
        f"Brand constraints: {brief['brand_constraints'] or 'none provided'}. "
        f"Scenes: {scene_prompt}"
    )
    negative = (
        "Do not include guaranteed outcomes, best-product claims, invented discounts, "
        "unverified availability, health or safety claims, revenue promises, "
        "commission or cookie-duration details, or claims not supported by uploaded data."
    )
    return {
        "concise_generation_prompt": concise,
        "detailed_generation_prompt": detailed,
        "negative_prompt": negative,
    }


def build_provider_neutral_payload(brief, storyboard, prompts):
    return {
        "provider_neutral": True,
        "target_platform": brief["target_platform"],
        "duration_seconds": brief["duration_seconds"],
        "aspect_ratio": brief["aspect_ratio"],
        "creative_intent": brief["campaign_objective"],
        "scenes": storyboard,
        "concise_prompt": prompts["concise_generation_prompt"],
        "detailed_prompt": prompts["detailed_generation_prompt"],
        "negative_prompt": prompts["negative_prompt"],
        "disclosure": brief["disclosure_text"],
        "prohibited_elements": UNSUPPORTED_CLAIMS,
    }


def validate_creative_package(package):
    warnings = list(package.get("brief", {}).get("warnings", []))
    text_parts = [
        package.get("script_text", ""),
        package.get("prompts", {}).get("concise_generation_prompt", ""),
        package.get("prompts", {}).get("detailed_generation_prompt", ""),
    ]
    combined = "\n".join(text_parts)
    for pattern in UNSUPPORTED_CLAIM_PATTERNS:
        if pattern.search(combined):
            warnings.append(
                "Unsupported claim language was detected; review and remove it before use."
            )
            break

    storyboard = package.get("storyboard", [])
    duration = package.get("brief", {}).get("duration_seconds", 0)
    if storyboard:
        previous_end = 0
        for scene in storyboard:
            if scene["start_time"] != previous_end or scene["end_time"] <= scene["start_time"]:
                warnings.append("Storyboard timing has gaps, overlaps, or invalid ranges.")
                break
            previous_end = scene["end_time"]
        if previous_end != duration:
            warnings.append("Storyboard does not end at the selected duration.")
    return sorted(set(warnings))


def build_creative_package(product, offer=None, video_recommendation=None, settings=None):
    context = build_creative_context(product, offer, video_recommendation, settings)
    brief = build_video_brief(context)
    storyboard = build_storyboard(brief)
    script_text = build_script(brief, storyboard)
    prompts = build_generation_prompts(brief, storyboard)
    package = {
        "version": "1.8",
        "created_at": context["created_at"],
        "brief": brief,
        "storyboard": storyboard,
        "script_text": script_text,
        "prompts": prompts,
        "provider_neutral_payload": build_provider_neutral_payload(
            brief,
            storyboard,
            prompts,
        ),
    }
    package["validation_warnings"] = validate_creative_package(package)
    return package


def dataframe_csv_bytes(data):
    frame = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    return frame.to_csv(index=False).encode("utf-8")


def brief_csv_bytes(brief):
    rows = [{"field": key, "value": json.dumps(value) if isinstance(value, (list, dict)) else value} for key, value in brief.items()]
    return dataframe_csv_bytes(rows)


def json_bytes(data):
    return json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")


def text_bytes(text):
    return text.encode("utf-8")


def package_zip_bytes(package):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("video_brief.json", json_bytes(package["brief"]))
        archive.writestr("video_brief.csv", brief_csv_bytes(package["brief"]))
        archive.writestr("script.txt", text_bytes(package["script_text"]))
        archive.writestr("storyboard.csv", dataframe_csv_bytes(package["storyboard"]))
        archive.writestr("storyboard.json", json_bytes(package["storyboard"]))
        archive.writestr(
            "generation_prompt.txt",
            text_bytes(
                package["prompts"]["concise_generation_prompt"]
                + "\n\n"
                + package["prompts"]["detailed_generation_prompt"]
                + "\n\nNegative prompt:\n"
                + package["prompts"]["negative_prompt"]
            ),
        )
        archive.writestr("creative_package.json", json_bytes(package))
    return buffer.getvalue()
