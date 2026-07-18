"""Offline tests for deterministic modification validation."""

from llm_pipeline.models import ModificationEdit, ModificationObject
from llm_pipeline.validation import validate_modification


def make_mod(reasoning="Improves flavor", edits=None, mod_type="addition"):
    return ModificationObject(
        modification_type=mod_type,
        reasoning=reasoning,
        edits=edits
        or [
            ModificationEdit(
                target="ingredients",
                operation="add_after",
                find="1 teaspoon salt",
                add="1 teaspoon cinnamon",
            )
        ],
    )


def test_accepts_concrete_tested_change():
    mod = make_mod()
    review = "I added a teaspoon of cinnamon and it was delicious."
    assert validate_modification(mod, review).is_valid


def test_rejects_hypothetical_next_time_reasoning():
    mod = make_mod(reasoning="Next time I will add more broth for thinner soup")
    review = "Great soup. Next time I will add more broth."
    result = validate_modification(mod, review)
    assert not result.is_valid
    assert "untested" in result.reason or "future" in result.reason


def test_rejects_review_with_only_future_intentions():
    """'Next time I'll use more broth' with no past-tense action = untested."""
    mod = make_mod(
        reasoning="More broth makes it less thick",
        edits=[
            ModificationEdit(
                target="ingredients",
                operation="replace",
                find="3 cups chicken broth",
                replace="4 cups chicken broth",
            )
        ],
        mod_type="quantity_adjustment",
    )
    review = "Very thick. Next time more broth."
    result = validate_modification(mod, review)
    assert not result.is_valid


def test_accepts_tested_change_even_when_review_also_has_future_plans():
    """'I added X. Next time I'll try Y' — the tested X part is valid."""
    mod = make_mod()
    review = "I added a teaspoon of cinnamon. Next time I'll try nutmeg too."
    assert validate_modification(mod, review).is_valid


def test_rejects_vague_quantity_without_number():
    mod = make_mod(
        edits=[
            ModificationEdit(
                target="ingredients",
                operation="add_after",
                find="3 cups chicken broth",
                add="more broth",
            )
        ]
    )
    review = "I used more broth."
    result = validate_modification(mod, review)
    assert not result.is_valid
    assert "vague" in result.reason


def test_rejects_prose_as_ingredient():
    mod = make_mod(
        edits=[
            ModificationEdit(
                target="ingredients",
                operation="add_after",
                find="3 cups chicken broth",
                add="Use more broth next time.",
            )
        ]
    )
    review = "Use more broth next time."
    result = validate_modification(mod, review)
    assert not result.is_valid


def test_rejects_replace_without_replacement_text():
    mod = make_mod(
        edits=[
            ModificationEdit(
                target="ingredients",
                operation="replace",
                find="1 cup white sugar",
                replace=None,
            )
        ],
        mod_type="quantity_adjustment",
    )
    result = validate_modification(mod, "I halved the sugar.")
    assert not result.is_valid
    assert "no replacement text" in result.reason


def test_rejects_add_after_without_add_text():
    mod = make_mod(
        edits=[
            ModificationEdit(
                target="ingredients",
                operation="add_after",
                find="2 eggs",
                add=None,
            )
        ]
    )
    result = validate_modification(mod, "I added an egg yolk.")
    assert not result.is_valid


def test_rejects_empty_edits():
    mod = ModificationObject(
        modification_type="addition", reasoning="x", edits=[]
    )
    result = validate_modification(mod, "I added stuff.")
    assert not result.is_valid
