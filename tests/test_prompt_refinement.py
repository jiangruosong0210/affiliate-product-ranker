import json
import unittest

from creative_planning import build_creative_package
from prompt_refinement import (
    OpenRouterRefinementResponse,
    OpenRouterSettings,
    load_openrouter_settings,
    package_signature,
    parse_refinement_json,
    refine_prompt_with_openrouter,
    validate_refinement_payload,
)
from video_generation_provider import MockVideoGenerationProvider
from video_generation_service import (
    build_video_generation_request,
    refresh_video_generation,
    submit_video_generation,
)


def product_row():
    return {
        "product_id": "P001",
        "product_name": "AI Resume Builder",
        "category": "Career Software",
        "profit_potential_score": 82.5,
        "product_url": "https://example.com/product",
    }


def make_package():
    return build_creative_package(
        product_row(),
        settings={
            "target_platform": "TikTok",
            "duration_seconds": 20,
            "aspect_ratio": "9:16",
        },
    )


def make_settings(api_key="test-key", timeout=3, max_length=4000):
    return OpenRouterSettings(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_model="openai/gpt-oss-20b:free",
        model_options=[
            "openai/gpt-oss-20b:free",
            "nvidia/nemotron-3-super-120b-a12b:free",
        ],
        timeout_seconds=timeout,
        max_prompt_length=max_length,
    )


def valid_response(prompt):
    return json.dumps(
        {
            "refined_prompt": prompt,
            "refinement_summary": ["Improved pacing."],
            "unsupported_claims_removed": [],
            "warnings": [],
        }
    )


def valid_openrouter_response(prompt, finish_reason="stop"):
    text = valid_response(prompt)
    return OpenRouterRefinementResponse(
        content=text,
        http_status=200,
        finish_reason=finish_reason,
        latency_seconds=1.25,
        response_length=len(text),
        model="openai/gpt-oss-20b:free",
        used_structured_output=True,
    )


class PromptRefinementTests(unittest.TestCase):
    def setUp(self):
        self.package = make_package()
        self.original_prompt = build_video_generation_request(self.package).prompt
        self.refined_prompt = (
            "Product: AI Resume Builder. Use clear camera movement, consistent "
            "screen mockups, and a measured pace for a TikTok short. Keep all "
            "claims limited to uploaded product information. End with the CTA: "
            "Learn more before you decide."
        )

    def test_no_api_key_falls_back_to_original_prompt(self):
        result = refine_prompt_with_openrouter(
            self.package,
            self.original_prompt,
            "openai/gpt-oss-20b:free",
            make_settings(api_key=""),
            client=lambda *_: self.fail("client should not be called"),
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.selected_prompt, self.original_prompt)
        self.assertEqual(result.status, "missing_api_key")

    def test_valid_configuration_loads_from_environment(self):
        env = {
            "OPENROUTER_API_KEY": "secret",
            "OPENROUTER_REFINEMENT_MODEL": "nvidia/nemotron-3-super-120b-a12b:free",
            "OPENROUTER_TIMEOUT_SECONDS": "7",
            "OPENROUTER_MAX_PROMPT_LENGTH": "1234",
        }
        settings = load_openrouter_settings(secrets={}, environ=env)
        self.assertEqual(settings.api_key, "secret")
        self.assertEqual(settings.default_model, "nvidia/nemotron-3-super-120b-a12b:free")
        self.assertEqual(settings.timeout_seconds, 7)
        self.assertEqual(settings.max_prompt_length, 1234)

    def test_successful_structured_response_is_accepted(self):
        result = refine_prompt_with_openrouter(
            self.package,
            self.original_prompt,
            "openai/gpt-oss-20b:free",
            make_settings(),
            client=lambda *_: valid_openrouter_response(self.refined_prompt),
        )
        self.assertTrue(result.accepted)
        self.assertEqual(result.selected_prompt, self.refined_prompt)
        self.assertEqual(result.status, "accepted")
        self.assertEqual(result.provider_metadata["finish_reason"], "stop")
        self.assertEqual(result.provider_metadata["http_status"], 200)

    def test_valid_plain_json_response_parser(self):
        payload = parse_refinement_json(valid_response(self.refined_prompt))
        self.assertEqual(payload["refined_prompt"], self.refined_prompt)

    def test_json_inside_markdown_fence_is_accepted(self):
        fenced = f"```json\n{valid_response(self.refined_prompt)}\n```"
        payload = parse_refinement_json(fenced)
        self.assertEqual(payload["refined_prompt"], self.refined_prompt)

    def test_text_before_json_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_refinement_json(f"Here is the JSON:\n{valid_response(self.refined_prompt)}")

    def test_truncated_json_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_refinement_json(valid_response(self.refined_prompt)[:-8])

    def test_finish_reason_length_falls_back(self):
        result = refine_prompt_with_openrouter(
            self.package,
            self.original_prompt,
            "openai/gpt-oss-20b:free",
            make_settings(),
            client=lambda *_: valid_openrouter_response(
                self.refined_prompt,
                finish_reason="length",
            ),
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.status, "truncated")
        self.assertEqual(result.selected_prompt, self.original_prompt)

    def test_missing_content_falls_back(self):
        result = refine_prompt_with_openrouter(
            self.package,
            self.original_prompt,
            "openai/gpt-oss-20b:free",
            make_settings(),
            client=lambda *_: OpenRouterRefinementResponse(
                content="",
                http_status=200,
                finish_reason="stop",
                response_length=0,
            ),
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.status, "missing_content")

    def test_malformed_json_falls_back(self):
        result = refine_prompt_with_openrouter(
            self.package,
            self.original_prompt,
            "openai/gpt-oss-20b:free",
            make_settings(),
            client=lambda *_: "not json",
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.selected_prompt, self.original_prompt)
        self.assertIn("valid JSON", result.error_message)

    def test_malformed_openrouter_payload_falls_back(self):
        result = refine_prompt_with_openrouter(
            self.package,
            self.original_prompt,
            "openai/gpt-oss-20b:free",
            make_settings(),
            client=lambda *_: OpenRouterRefinementResponse(
                content="[]",
                http_status=200,
                finish_reason="stop",
                response_length=2,
            ),
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.status, "provider_error")
        self.assertEqual(result.selected_prompt, self.original_prompt)

    def test_missing_required_field_is_rejected(self):
        payload = {
            "refinement_summary": [],
            "unsupported_claims_removed": [],
            "warnings": [],
        }
        errors = validate_refinement_payload(
            payload,
            self.package,
            self.original_prompt,
            4000,
        )
        self.assertTrue(any("refined_prompt" in error for error in errors))

    def test_empty_refined_prompt_is_rejected(self):
        payload = {
            "refined_prompt": " ",
            "refinement_summary": [],
            "unsupported_claims_removed": [],
            "warnings": [],
        }
        errors = validate_refinement_payload(
            payload,
            self.package,
            self.original_prompt,
            4000,
        )
        self.assertIn("The refined prompt was empty.", errors)

    def test_timeout_falls_back(self):
        def timeout_client(*_):
            raise TimeoutError("OpenRouter request timed out.")

        result = refine_prompt_with_openrouter(
            self.package,
            self.original_prompt,
            "openai/gpt-oss-20b:free",
            make_settings(),
            client=timeout_client,
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.status, "timeout")

    def test_http_error_messages_fall_back(self):
        for status in [401, 402, 429, 500]:
            with self.subTest(status=status):
                result = refine_prompt_with_openrouter(
                    self.package,
                    self.original_prompt,
                    "openai/gpt-oss-20b:free",
                    make_settings(),
                    client=lambda *_, status=status: (_ for _ in ()).throw(
                        RuntimeError(f"HTTP {status}.")
                    ),
                )
                self.assertFalse(result.accepted)
                self.assertEqual(result.selected_prompt, self.original_prompt)

    def test_unsupported_claim_introduced_is_rejected(self):
        payload = {
            "refined_prompt": "Product: AI Resume Builder. Guarantee job offers.",
            "refinement_summary": [],
            "unsupported_claims_removed": [],
            "warnings": [],
        }
        errors = validate_refinement_payload(
            payload,
            self.package,
            self.original_prompt,
            4000,
        )
        self.assertTrue(any("unsupported claim" in error for error in errors))

    def test_invented_discount_is_rejected(self):
        payload = {
            "refined_prompt": "Product: AI Resume Builder. Mention a 50% off coupon.",
            "refinement_summary": [],
            "unsupported_claims_removed": [],
            "warnings": [],
        }
        errors = validate_refinement_payload(
            payload,
            self.package,
            self.original_prompt,
            4000,
        )
        self.assertTrue(any("discount" in error for error in errors))

    def test_product_identity_change_is_rejected(self):
        payload = {
            "refined_prompt": "Product: Budget Tax Calculator. Use a clean demo.",
            "refinement_summary": [],
            "unsupported_claims_removed": [],
            "warnings": [],
        }
        errors = validate_refinement_payload(
            payload,
            self.package,
            self.original_prompt,
            4000,
        )
        self.assertTrue(any("product identity" in error for error in errors))

    def test_disclosure_removed_is_rejected_when_original_contains_it(self):
        package = make_package()
        package["brief"]["disclosure_text"] = "Affiliate disclosure: sponsored link."
        original = (
            build_video_generation_request(package).prompt
            + " Affiliate disclosure: sponsored link."
        )
        payload = {
            "refined_prompt": "Product: AI Resume Builder. Show a simple demo.",
            "refinement_summary": [],
            "unsupported_claims_removed": [],
            "warnings": [],
        }
        errors = validate_refinement_payload(payload, package, original, 4000)
        self.assertTrue(any("disclosure" in error for error in errors))

    def test_explicit_prompt_selection_changes_request_metadata(self):
        original_request = build_video_generation_request(self.package)
        refined_request = build_video_generation_request(
            self.package,
            prompt_override=self.refined_prompt,
        )
        self.assertNotEqual(original_request.request_id, refined_request.request_id)
        self.assertEqual(refined_request.prompt, self.refined_prompt)
        self.assertEqual(refined_request.metadata["prompt_source"], "refined")

    def test_duplicate_refinement_prevention_state_flag(self):
        state = {"prompt_refinement_in_progress": True}
        self.assertTrue(state["prompt_refinement_in_progress"])
        state["prompt_refinement_in_progress"] = False
        self.assertFalse(state["prompt_refinement_in_progress"])

    def test_creative_package_change_invalidates_refinement_signature(self):
        first = package_signature(self.package)
        changed = make_package()
        changed["brief"]["product_name"] = "AI Cover Letter Builder"
        second = package_signature(changed)
        self.assertNotEqual(first, second)

    def test_session_state_persistence_shape(self):
        state = {
            "prompt_refinement_active_choice": "refined",
            "prompt_refinement_refined_prompt": self.refined_prompt,
        }
        self.assertEqual(state["prompt_refinement_active_choice"], "refined")
        self.assertIn("AI Resume Builder", state["prompt_refinement_refined_prompt"])

    def test_stored_result_reused_without_second_api_call(self):
        calls = {"count": 0}

        def client(*_):
            calls["count"] += 1
            return valid_openrouter_response(self.refined_prompt)

        result = refine_prompt_with_openrouter(
            self.package,
            self.original_prompt,
            "openai/gpt-oss-20b:free",
            make_settings(),
            client=client,
        )
        state = {"prompt_refinement_result": result}
        selected = state["prompt_refinement_result"].selected_prompt
        self.assertEqual(selected, self.refined_prompt)
        self.assertEqual(calls["count"], 1)

    def test_radio_prompt_selection_does_not_call_api(self):
        calls = {"count": 0}

        def client(*_):
            calls["count"] += 1
            return valid_openrouter_response(self.refined_prompt)

        state = {
            "prompt_refinement_active_choice": "refined",
            "prompt_refinement_refined_prompt": self.refined_prompt,
        }
        request = build_video_generation_request(
            self.package,
            prompt_override=state["prompt_refinement_refined_prompt"],
        )
        self.assertEqual(request.prompt, self.refined_prompt)
        self.assertEqual(calls["count"], 0)

    def test_reset_does_not_call_api(self):
        calls = {"count": 0}
        state = {
            "prompt_refinement_result": object(),
            "prompt_refinement_refined_prompt": self.refined_prompt,
        }
        state.clear()
        self.assertEqual(state, {})
        self.assertEqual(calls["count"], 0)

    def test_mock_job_refresh_does_not_call_refinement_api(self):
        calls = {"count": 0}
        provider = MockVideoGenerationProvider()
        request = build_video_generation_request(self.package)
        job, _, error = submit_video_generation(provider, request)
        self.assertIsNone(error)
        refresh_video_generation(provider, job)
        self.assertEqual(calls["count"], 0)

    def test_toggle_disabled_means_original_request_still_works(self):
        refinement_enabled = False
        request = build_video_generation_request(self.package)
        self.assertFalse(refinement_enabled)
        self.assertEqual(request.metadata["prompt_source"], "original")


if __name__ == "__main__":
    unittest.main()
