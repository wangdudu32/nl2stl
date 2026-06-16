from jsonschema import Draft202012Validator

from nl2stl_app.config import RuntimeCatalog
from nl2stl_app.services import _format_schema_errors, _normalize_for_schema


def test_candidate_explanation_is_compacted_before_schema_validation():
    schema = RuntimeCatalog().schema("candidate_set")
    result = {
        "candidates": [
            {
                "id": "urban_low_speed",
                "value": "ego_speed <= 30",
                "explanation": (
                    "In urban autonomous driving scenarios, speeds at or below "
                    "30 km/h are typically classified as low speed for safety "
                    "and control."
                ),
                "source_type": "search",
                "source_reference": "https://example.com/low-speed",
                "canonical": "ego_speed<=30",
            }
        ],
        "insufficient_reason": "",
    }

    _normalize_for_schema("candidate_set", result, schema)

    assert len(result["candidates"][0]["explanation"]) <= 120
    assert Draft202012Validator(schema).is_valid(result)


def test_schema_error_message_includes_prompt_and_path():
    schema = RuntimeCatalog().schema("candidate_set")
    result = {
        "candidates": [
            {
                "id": "urban_low_speed",
                "value": "ego_speed <= 30",
                "explanation": "x" * 121,
                "source_type": "search",
                "source_reference": "https://example.com/low-speed",
                "canonical": "ego_speed<=30",
            }
        ],
        "insufficient_reason": "",
    }

    errors = list(Draft202012Validator(schema).iter_errors(result))
    message = _format_schema_errors("generate_candidates_web", errors)

    assert "generate_candidates_web candidates[0].explanation" in message
    assert "max 120" in message
