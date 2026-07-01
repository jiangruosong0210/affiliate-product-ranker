import json
import os
import re
import socket
from time import perf_counter
import urllib.error
import urllib.request
from dataclasses import dataclass, field


OPENROUTER_REFINEMENT_CONFIG = {
    "base_url": "https://openrouter.ai/api/v1",
    "default_model": "openai/gpt-oss-20b:free",
    "model_options": [
        "openai/gpt-oss-20b:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
    ],
    "timeout_seconds": 40,
    "max_prompt_length": 4000,
    "max_response_tokens": 1400,
    "structured_output_models": {
        "openai/gpt-oss-20b:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
    },
}

REQUIRED_REFINEMENT_FIELDS = {
    "refined_prompt": str,
    "refinement_summary": list,
    "unsupported_claims_removed": list,
    "warnings": list,
}

PROHIBITED_CLAIM_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bguarantee[sd]?\b",
        r"\bguaranteed results?\b",
        r"\bguaranteed income\b",
        r"\bguaranteed job\b",
        r"\b#\s*1\b",
        r"\bnumber\s+one\b",
        r"\bbest\s+(in|on|for|overall|product|tool|platform)\b",
        r"\bmarket\s+leader\b",
        r"\bofficially\s+endorsed\b",
        r"\bproven\s+to\b",
        r"\baward[- ]winning\b",
        r"\btestimonial\b",
        r"\bhealth\s+claim\b",
        r"\bsafety\s+claim\b",
    ]
]

DISCOUNT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bdiscount\b",
        r"\bcoupon\b",
        r"\bpromo\s+code\b",
        r"\bsale\b",
        r"\bfree\s+trial\b",
        r"\b\d+%\s*off\b",
        r"\$\d+\s*off\b",
    ]
]


@dataclass(frozen=True)
class OpenRouterSettings:
    api_key: str
    base_url: str
    default_model: str
    model_options: list[str]
    timeout_seconds: int
    max_prompt_length: int


@dataclass
class RefinementResult:
    accepted: bool
    original_prompt: str
    selected_prompt: str
    refined_prompt: str = ""
    refinement_summary: list[str] = field(default_factory=list)
    unsupported_claims_removed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    model: str = ""
    status: str = "not_requested"
    error_message: str = ""
    provider_metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class OpenRouterRefinementResponse:
    content: str
    http_status: int | None = None
    finish_reason: str = ""
    latency_seconds: float | None = None
    response_length: int = 0
    model: str = ""
    used_structured_output: bool = False


def get_secret_value(secrets, key):
    if secrets is None:
        return ""
    try:
        return str(secrets.get(key, "") or "")
    except Exception:
        return ""


def load_openrouter_settings(secrets=None, environ=None):
    environ = environ or os.environ
    api_key = environ.get("OPENROUTER_API_KEY") or get_secret_value(
        secrets,
        "OPENROUTER_API_KEY",
    )
    base_url = (
        environ.get("OPENROUTER_BASE_URL")
        or get_secret_value(secrets, "OPENROUTER_BASE_URL")
        or OPENROUTER_REFINEMENT_CONFIG["base_url"]
    )
    default_model = (
        environ.get("OPENROUTER_REFINEMENT_MODEL")
        or get_secret_value(secrets, "OPENROUTER_REFINEMENT_MODEL")
        or OPENROUTER_REFINEMENT_CONFIG["default_model"]
    )
    timeout_seconds = int(
        environ.get("OPENROUTER_TIMEOUT_SECONDS")
        or get_secret_value(secrets, "OPENROUTER_TIMEOUT_SECONDS")
        or OPENROUTER_REFINEMENT_CONFIG["timeout_seconds"]
    )
    max_prompt_length = int(
        environ.get("OPENROUTER_MAX_PROMPT_LENGTH")
        or get_secret_value(secrets, "OPENROUTER_MAX_PROMPT_LENGTH")
        or OPENROUTER_REFINEMENT_CONFIG["max_prompt_length"]
    )
    model_options = list(OPENROUTER_REFINEMENT_CONFIG["model_options"])
    if default_model not in model_options:
        model_options.insert(0, default_model)
    return OpenRouterSettings(
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        default_model=default_model,
        model_options=model_options,
        timeout_seconds=timeout_seconds,
        max_prompt_length=max_prompt_length,
    )


def has_openrouter_key(secrets=None, environ=None):
    return bool(load_openrouter_settings(secrets=secrets, environ=environ).api_key)


def build_storyboard_summary(storyboard):
    parts = []
    for scene in storyboard or []:
        parts.append(
            f"{scene.get('start_time', '')}-{scene.get('end_time', '')}s: "
            f"{scene.get('visual_direction', scene.get('scene_goal', ''))}"
        )
    return "\n".join(parts)


def valid_offer_summary(brief):
    platform = brief.get("selected_offer_platform") or brief.get("offer_platform")
    payout = brief.get("payout_type")
    if not platform and not payout:
        return "No validated offer details are available."
    return json.dumps(
        {
            "platform": platform,
            "payout_type": payout,
            "offer_status": brief.get("offer_status"),
        },
        ensure_ascii=False,
    )


def build_refinement_messages(creative_package, original_prompt):
    brief = creative_package.get("brief", {})
    payload = creative_package.get("provider_neutral_payload", {})
    prompt_context = {
        "product_name": brief.get("product_name", ""),
        "campaign_objective": brief.get("campaign_objective", ""),
        "platform": brief.get("target_platform", ""),
        "duration_seconds": payload.get("duration_seconds") or brief.get("duration_seconds"),
        "aspect_ratio": payload.get("aspect_ratio") or brief.get("aspect_ratio"),
        "original_detailed_prompt": original_prompt,
        "storyboard_summary": build_storyboard_summary(
            creative_package.get("storyboard", []),
        ),
        "supported_product_features": brief.get("supported_features", []),
        "offer_information": valid_offer_summary(brief),
        "unsupported_claim_rules": payload.get("prohibited_elements", []),
        "brand_constraints": brief.get("brand_constraints", ""),
        "disclosure_metadata": brief.get("disclosure_text", ""),
        "recommended_cta": brief.get("recommended_cta", ""),
    }
    system_message = (
        "You refine model-neutral text-to-video prompts. Improve clarity, camera "
        "instructions, transitions, pacing, and visual consistency only. Do not "
        "redesign the product-ranking, offer-comparison, video-analysis, or "
        "creative-package workflow. Do not invent discounts, prices, features, "
        "performance claims, health or safety claims, guaranteed results, "
        "popularity claims, brand positioning, testimonials, or awards. Return "
        "only one JSON object. Do not wrap it in Markdown. Do not include "
        "explanatory text before or after the JSON."
    )
    user_message = (
        "Return only valid JSON with exactly these keys: refined_prompt, "
        "refinement_summary, unsupported_claims_removed, and warnings. "
        "refinement_summary, unsupported_claims_removed, and warnings must be "
        "JSON arrays of strings, even when there is only one item. Use [] for "
        "an empty list. Example shape: {\"refined_prompt\":\"...\","
        "\"refinement_summary\":[\"...\"],\"unsupported_claims_removed\":[],"
        "\"warnings\":[]}. "
        "The refined_prompt must preserve the product name, CTA when present, "
        "and disclosure metadata when present. Context:\n"
        f"{json.dumps(prompt_context, ensure_ascii=False, indent=2)}"
    )
    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
    ]


def build_response_format():
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "prompt_refinement",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "refined_prompt": {"type": "string"},
                    "refinement_summary": {"type": "array", "items": {"type": "string"}},
                    "unsupported_claims_removed": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "warnings": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "refined_prompt",
                    "refinement_summary",
                    "unsupported_claims_removed",
                    "warnings",
                ],
                "additionalProperties": False,
            },
        },
    }


def call_openrouter_refinement(settings, model, messages):
    url = f"{settings.base_url}/chat/completions"
    uses_structured_output = model in OPENROUTER_REFINEMENT_CONFIG[
        "structured_output_models"
    ]
    request_body = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": OPENROUTER_REFINEMENT_CONFIG["max_response_tokens"],
    }
    if uses_structured_output:
        request_body["response_format"] = build_response_format()
        request_body["provider"] = {"require_parameters": True}
    request = urllib.request.Request(
        url,
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
            "X-OpenRouter-Title": "Affiliate Product Ranker Prompt Refinement",
        },
        method="POST",
    )
    started_at = perf_counter()
    try:
        with urllib.request.urlopen(
            request,
            timeout=settings.timeout_seconds,
        ) as response:
            http_status = response.status
            data = json.loads(response.read().decode("utf-8"))
    except socket.timeout as exc:
        raise TimeoutError("OpenRouter request timed out.") from exc
    except urllib.error.HTTPError as exc:
        status_messages = {
            401: "OpenRouter authentication failed.",
            402: "OpenRouter account has insufficient credits or a billing restriction.",
            429: "OpenRouter free-model rate limit was reached.",
        }
        if exc.code >= 500:
            message = "OpenRouter is temporarily unavailable."
        else:
            message = status_messages.get(exc.code, "OpenRouter request failed.")
        raise RuntimeError(f"{message} HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("OpenRouter could not be reached.") from exc

    choice = data.get("choices", [{}])[0]
    content = choice.get("message", {}).get("content", "")
    finish_reason = choice.get("finish_reason") or ""
    return OpenRouterRefinementResponse(
        content=content or "",
        http_status=http_status,
        finish_reason=finish_reason,
        latency_seconds=round(perf_counter() - started_at, 2),
        response_length=len(content or ""),
        model=data.get("model", model),
        used_structured_output=uses_structured_output,
    )


def response_to_text(response):
    if isinstance(response, OpenRouterRefinementResponse):
        return response.content
    return str(response or "")


def response_metadata(response):
    if not isinstance(response, OpenRouterRefinementResponse):
        return {"response_length": len(str(response or ""))}
    return {
        "http_status": response.http_status,
        "finish_reason": response.finish_reason,
        "latency_seconds": response.latency_seconds,
        "response_length": response.response_length,
        "model": response.model,
        "used_structured_output": response.used_structured_output,
    }


def strip_single_json_fence(response_text):
    text = str(response_text or "").strip()
    fence_pattern = re.compile(r"^```(?:json|JSON)?\s*(\{.*\})\s*```$", re.DOTALL)
    match = fence_pattern.match(text)
    if match:
        return match.group(1).strip()
    return text


def parse_refinement_json(response_text):
    text = strip_single_json_fence(response_text)
    if not text:
        raise ValueError("The refinement response did not contain JSON content.")
    decoder = json.JSONDecoder()
    try:
        payload, end_index = decoder.raw_decode(text)
    except json.JSONDecodeError as exc:
        raise ValueError("The refinement response was not valid JSON.") from exc
    if text[end_index:].strip():
        raise ValueError(
            "The refinement response included extra text after the JSON object."
        )
    if not isinstance(payload, dict):
        raise ValueError("The refinement response must be a JSON object.")
    return payload


def normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def contains_pattern(patterns, text):
    return any(pattern.search(text) for pattern in patterns)


def has_new_discount(original_prompt, refined_prompt):
    if contains_pattern(DISCOUNT_PATTERNS, refined_prompt) and not contains_pattern(
        DISCOUNT_PATTERNS,
        original_prompt,
    ):
        return True
    return False


def validate_refinement_payload(payload, creative_package, original_prompt, max_prompt_length):
    errors = []
    if not isinstance(payload, dict):
        return ["The refinement response must be a JSON object."]

    for field_name, expected_type in REQUIRED_REFINEMENT_FIELDS.items():
        if field_name not in payload:
            errors.append(f"Missing required field: {field_name}.")
        elif not isinstance(payload[field_name], expected_type):
            errors.append(f"Field {field_name} has the wrong type.")

    if errors:
        return errors

    refined_prompt = payload["refined_prompt"].strip()
    if not refined_prompt:
        errors.append("The refined prompt was empty.")
    if len(refined_prompt) > max_prompt_length:
        errors.append("The refined prompt was too long.")

    brief = creative_package.get("brief", {})
    product_name = brief.get("product_name", "")
    if product_name and normalize_text(product_name) not in normalize_text(refined_prompt):
        errors.append("The refined prompt changed or removed the product identity.")

    recommended_cta = brief.get("recommended_cta", "")
    if recommended_cta and normalize_text(recommended_cta) in normalize_text(original_prompt):
        if normalize_text(recommended_cta) not in normalize_text(refined_prompt):
            errors.append("The refined prompt removed the enabled CTA.")

    disclosure_text = brief.get("disclosure_text", "")
    if disclosure_text and normalize_text(disclosure_text) in normalize_text(original_prompt):
        if normalize_text(disclosure_text) not in normalize_text(refined_prompt):
            errors.append("The refined prompt removed disclosure metadata.")

    if contains_pattern(PROHIBITED_CLAIM_PATTERNS, refined_prompt):
        errors.append("The refined prompt introduced unsupported claim language.")

    if has_new_discount(original_prompt, refined_prompt):
        errors.append("The refined prompt introduced an unsupported discount or offer detail.")

    for list_field in ["refinement_summary", "unsupported_claims_removed", "warnings"]:
        if not all(isinstance(item, str) for item in payload[list_field]):
            errors.append(f"All {list_field} entries must be text.")

    return errors


def refine_prompt_with_openrouter(
    creative_package,
    original_prompt,
    model,
    settings,
    client=call_openrouter_refinement,
):
    if not settings.api_key:
        return RefinementResult(
            accepted=False,
            original_prompt=original_prompt,
            selected_prompt=original_prompt,
            model=model,
            status="missing_api_key",
            error_message="OpenRouter is not configured. The original prompt is still available.",
            provider_metadata={"configured": False},
        )
    messages = build_refinement_messages(creative_package, original_prompt)
    metadata = {}
    try:
        response = client(settings, model, messages)
        metadata = response_metadata(response)
        if metadata.get("finish_reason") == "length":
            return RefinementResult(
                accepted=False,
                original_prompt=original_prompt,
                selected_prompt=original_prompt,
                model=model,
                status="truncated",
                error_message=(
                    "The refinement response was truncated. No refined prompt "
                    "was accepted."
                ),
                provider_metadata=metadata,
            )
        response_text = response_to_text(response)
        if not response_text.strip():
            return RefinementResult(
                accepted=False,
                original_prompt=original_prompt,
                selected_prompt=original_prompt,
                model=model,
                status="missing_content",
                error_message=(
                    "OpenRouter returned no message content. No refined prompt "
                    "was accepted."
                ),
                provider_metadata=metadata,
            )
        payload = parse_refinement_json(response_text)
        errors = validate_refinement_payload(
            payload,
            creative_package,
            original_prompt,
            settings.max_prompt_length,
        )
        if errors:
            return RefinementResult(
                accepted=False,
                original_prompt=original_prompt,
                selected_prompt=original_prompt,
                model=model,
                status="validation_failed",
                error_message="No refined prompt was accepted.",
                warnings=errors,
                provider_metadata=metadata,
            )
        return RefinementResult(
            accepted=True,
            original_prompt=original_prompt,
            selected_prompt=payload["refined_prompt"].strip(),
            refined_prompt=payload["refined_prompt"].strip(),
            refinement_summary=payload["refinement_summary"],
            unsupported_claims_removed=payload["unsupported_claims_removed"],
            warnings=payload["warnings"],
            model=model,
            status="accepted",
            provider_metadata=metadata,
        )
    except TimeoutError as exc:
        status = "timeout"
        message = str(exc)
    except Exception as exc:
        status = "provider_error"
        message = str(exc)

    return RefinementResult(
        accepted=False,
        original_prompt=original_prompt,
        selected_prompt=original_prompt,
        model=model,
        status=status,
        error_message=f"{message} No refined prompt was accepted.",
        provider_metadata=metadata,
    )


def package_signature(creative_package):
    relevant = {
        "brief": creative_package.get("brief", {}),
        "storyboard": creative_package.get("storyboard", []),
        "prompts": creative_package.get("prompts", {}),
        "provider_neutral_payload": creative_package.get("provider_neutral_payload", {}),
    }
    return json.dumps(relevant, sort_keys=True, ensure_ascii=False)
