"""Offline tests for enhanced recipe generation, summary accuracy, attribution."""

from llm_pipeline.enhanced_recipe_generator import EnhancedRecipeGenerator
from llm_pipeline.models import (
    ChangeRecord,
    ModificationEdit,
    ModificationObject,
    Recipe,
    Review,
)


def make_recipe():
    return Recipe(
        recipe_id="10813",
        title="Best Chocolate Chip Cookies",
        ingredients=["1 cup butter", "0.5 cup white sugar"],
        instructions=["Mix.", "Bake."],
        prep_time="20 mins",
        cook_time="10 mins",
        total_time="1 hr",
        servings="24",
    )


def make_applied(n=2):
    applied = []
    for i in range(n):
        modification = ModificationObject(
            modification_type="quantity_adjustment" if i == 0 else "addition",
            reasoning=f"reason {i}",
            edits=[
                ModificationEdit(
                    target="ingredients",
                    operation="replace",
                    find=f"x{i}",
                    replace=f"y{i}",
                )
            ],
        )
        rev = Review(text=f"review {i}", rating=5, has_modification=True)
        records = [
            ChangeRecord(
                type="ingredient",
                from_text=f"x{i}",
                to_text=f"y{i}",
                operation="replace",
            )
        ]
        applied.append((modification, rev, records))
    return applied


def test_one_attribution_record_per_modification():
    gen = EnhancedRecipeGenerator()
    recipe = make_recipe()
    applied = make_applied(3)
    enhanced = gen.generate_enhanced_recipe(recipe, recipe, applied)
    assert len(enhanced.modifications_applied) == 3
    assert [m.source_review.text for m in enhanced.modifications_applied] == [
        "review 0",
        "review 1",
        "review 2",
    ]


def test_summary_totals_match_change_records():
    gen = EnhancedRecipeGenerator()
    recipe = make_recipe()
    applied = make_applied(2)
    enhanced = gen.generate_enhanced_recipe(recipe, recipe, applied)
    assert enhanced.enhancement_summary.total_changes == 2
    assert set(enhanced.enhancement_summary.change_types) == {
        "quantity_adjustment",
        "addition",
    }


def test_metadata_flows_to_output():
    gen = EnhancedRecipeGenerator()
    recipe = make_recipe()
    enhanced = gen.generate_enhanced_recipe(recipe, recipe, make_applied(1))
    assert enhanced.prep_time == "20 mins"
    assert enhanced.cook_time == "10 mins"
    assert enhanced.total_time == "1 hr"
    assert enhanced.servings == "24"


def test_change_types_deterministic_order():
    gen = EnhancedRecipeGenerator()
    recipe = make_recipe()
    applied = make_applied(2)
    e1 = gen.generate_enhanced_recipe(recipe, recipe, applied)
    e2 = gen.generate_enhanced_recipe(recipe, recipe, applied)
    assert e1.enhancement_summary.change_types == e2.enhancement_summary.change_types
