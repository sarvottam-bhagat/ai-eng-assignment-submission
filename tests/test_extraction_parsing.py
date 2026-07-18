"""Offline tests for extraction response parsing (no API calls)."""

import json

import pytest
from pydantic import ValidationError

from llm_pipeline.tweak_extractor import TweakExtractor


def test_parses_multiple_atomic_modifications():
    """A bundled review response with 4 tweaks parses into 4 objects."""
    raw = json.dumps(
        {
            "modifications": [
                {
                    "modification_type": "quantity_adjustment",
                    "reasoning": "Chewier cookies from higher brown sugar ratio",
                    "edits": [
                        {
                            "target": "ingredients",
                            "operation": "replace",
                            "find": "1 cup white sugar",
                            "replace": "0.5 cup white sugar",
                        },
                        {
                            "target": "ingredients",
                            "operation": "replace",
                            "find": "1 cup packed brown sugar",
                            "replace": "1.5 cups packed brown sugar",
                        },
                    ],
                },
                {
                    "modification_type": "removal",
                    "reasoning": "Omitting water prevents spreading",
                    "edits": [
                        {
                            "target": "ingredients",
                            "operation": "remove",
                            "find": "2 teaspoons hot water",
                        }
                    ],
                },
                {
                    "modification_type": "addition",
                    "reasoning": "Cream of tartar helps cookies hold shape",
                    "edits": [
                        {
                            "target": "ingredients",
                            "operation": "add_after",
                            "find": "1 teaspoon baking soda",
                            "add": "1 teaspoon cream of tartar",
                        }
                    ],
                },
                {
                    "modification_type": "technique_change",
                    "reasoning": "Chilled dough spreads less",
                    "edits": [
                        {
                            "target": "instructions",
                            "operation": "add_after",
                            "find": "Blend in the flour mixture.",
                            "add": "Refrigerate the dough for 1 hour before baking.",
                        }
                    ],
                },
            ]
        }
    )

    result = TweakExtractor.parse_extraction_response(raw)
    assert len(result.modifications) == 4
    types = [m.modification_type for m in result.modifications]
    assert types == [
        "quantity_adjustment",
        "removal",
        "addition",
        "technique_change",
    ]


def test_parses_empty_modifications_list():
    result = TweakExtractor.parse_extraction_response('{"modifications": []}')
    assert result.modifications == []


def test_parses_legacy_single_object_format():
    raw = json.dumps(
        {
            "modification_type": "addition",
            "reasoning": "Extra yolk for chew",
            "edits": [
                {
                    "target": "ingredients",
                    "operation": "add_after",
                    "find": "2 eggs",
                    "add": "1 additional egg yolk",
                }
            ],
        }
    )
    result = TweakExtractor.parse_extraction_response(raw)
    assert len(result.modifications) == 1
    assert result.modifications[0].modification_type == "addition"


def test_rejects_malformed_json():
    with pytest.raises(json.JSONDecodeError):
        TweakExtractor.parse_extraction_response("not json at all")


def test_rejects_invalid_modification_type():
    raw = json.dumps(
        {
            "modifications": [
                {
                    "modification_type": "not_a_real_type",
                    "reasoning": "x",
                    "edits": [
                        {"target": "ingredients", "operation": "remove", "find": "y"}
                    ],
                }
            ]
        }
    )
    with pytest.raises(ValidationError):
        TweakExtractor.parse_extraction_response(raw)
