"""Offline tests for safe matching, conflicts, duplicates, and metadata."""

from llm_pipeline.models import ModificationEdit, ModificationObject, Recipe, Review
from llm_pipeline.recipe_modifier import RecipeModifier


def make_recipe():
    return Recipe(
        recipe_id="test1",
        title="Test Cookies",
        ingredients=[
            "1 cup butter, softened",
            "1 cup white sugar",
            "1 cup packed brown sugar",
            "2 eggs",
            "2 teaspoons hot water",
            "1 teaspoon salt",
        ],
        instructions=[
            "Preheat the oven to 350 degrees F (175 degrees C).",
            "Cream together the butter and sugars.",
            "Bake for about 10 minutes.",
        ],
        prep_time="20 mins",
        cook_time="10 mins",
        total_time="30 mins",
    )


def mod(mod_type, edits, reasoning="test"):
    return ModificationObject(
        modification_type=mod_type, reasoning=reasoning, edits=edits
    )


def review(text="I made this change."):
    return Review(text=text, has_modification=True)


class TestTargetResolution:
    def test_exact_match(self):
        m = RecipeModifier()
        idx, method = m.resolve_target("1 cup white sugar", ["1 cup white sugar", "2 eggs"])
        assert idx == 0 and method == "exact"

    def test_normalized_match(self):
        m = RecipeModifier()
        idx, method = m.resolve_target(
            "1 Cup White Sugar ", ["1 cup white sugar", "2 eggs"]
        )
        assert idx == 0 and method == "normalized"

    def test_unique_substring_match(self):
        m = RecipeModifier()
        idx, method = m.resolve_target("white sugar", ["1 cup white sugar", "2 eggs"])
        assert idx == 0 and method == "substring"

    def test_ambiguous_substring_rejected(self):
        m = RecipeModifier()
        idx, method = m.resolve_target(
            "sugar", ["1 cup white sugar", "1 cup brown sugar"]
        )
        assert idx is None and method == "ambiguous_substring"

    def test_missing_target_rejected(self):
        m = RecipeModifier()
        idx, method = m.resolve_target("chocolate chips", ["2 eggs"])
        assert idx is None and method == "not_found"


class TestSafeReplace:
    def test_fuzzy_similarity_never_overwrites_line(self):
        """A slightly-similar but different line must NOT be replaced."""
        recipe = make_recipe()
        m = RecipeModifier()
        bad = mod(
            "quantity_adjustment",
            [
                ModificationEdit(
                    target="ingredients",
                    operation="replace",
                    find="1.5 cups half-and-half (or whole milk)",  # not in recipe
                    replace="2 cups half-and-half",
                )
            ],
        )
        modified, applied = m.apply_modifications(recipe, [(bad, review())])
        assert applied == []
        assert modified.ingredients == recipe.ingredients  # untouched

    def test_substring_replace_preserves_rest_of_line(self):
        recipe = make_recipe()
        m = RecipeModifier()
        change = mod(
            "technique_change",
            [
                ModificationEdit(
                    target="instructions",
                    operation="replace",
                    find="350 degrees F",
                    replace="375 degrees F",
                )
            ],
        )
        modified, applied = m.apply_modifications(recipe, [(change, review())])
        assert len(applied) == 1
        assert modified.instructions[0] == "Preheat the oven to 375 degrees F (175 degrees C)."

    def test_noop_replace_not_recorded(self):
        recipe = make_recipe()
        m = RecipeModifier()
        noop = mod(
            "quantity_adjustment",
            [
                ModificationEdit(
                    target="ingredients",
                    operation="replace",
                    find="1 cup white sugar",
                    replace="1 cup white sugar",  # same text
                )
            ],
        )
        modified, applied = m.apply_modifications(recipe, [(noop, review())])
        assert applied == []


class TestConflictsAndDuplicates:
    def test_conflicting_edits_first_wins(self):
        recipe = make_recipe()
        m = RecipeModifier()
        first = mod(
            "quantity_adjustment",
            [
                ModificationEdit(
                    target="ingredients",
                    operation="replace",
                    find="1 cup white sugar",
                    replace="0.5 cup white sugar",
                )
            ],
        )
        second = mod(
            "quantity_adjustment",
            [
                ModificationEdit(
                    target="ingredients",
                    operation="replace",
                    find="0.5 cup white sugar",
                    replace="0.75 cup white sugar",
                )
            ],
        )
        modified, applied = m.apply_modifications(
            recipe, [(first, review("a")), (second, review("b"))]
        )
        assert len(applied) == 1  # only the first survives
        assert "0.5 cup white sugar" in modified.ingredients
        assert "0.75 cup white sugar" not in modified.ingredients

    def test_duplicate_addition_collapsed(self):
        recipe = make_recipe()
        m = RecipeModifier()
        add1 = mod(
            "addition",
            [
                ModificationEdit(
                    target="ingredients",
                    operation="add_after",
                    find="2 eggs",
                    add="1 additional egg yolk",
                )
            ],
        )
        add2 = mod(
            "addition",
            [
                ModificationEdit(
                    target="ingredients",
                    operation="add_after",
                    find="2 eggs",
                    add="1 additional egg yolk",  # same addition from another review
                )
            ],
        )
        modified, applied = m.apply_modifications(
            recipe, [(add1, review("a")), (add2, review("b"))]
        )
        assert len(applied) == 1
        assert modified.ingredients.count("1 additional egg yolk") == 1

    def test_independent_edits_both_apply(self):
        recipe = make_recipe()
        m = RecipeModifier()
        sugar = mod(
            "quantity_adjustment",
            [
                ModificationEdit(
                    target="ingredients",
                    operation="replace",
                    find="1 cup white sugar",
                    replace="0.5 cup white sugar",
                )
            ],
        )
        water = mod(
            "removal",
            [
                ModificationEdit(
                    target="ingredients",
                    operation="remove",
                    find="2 teaspoons hot water",
                )
            ],
        )
        modified, applied = m.apply_modifications(
            recipe, [(sugar, review("a")), (water, review("b"))]
        )
        assert len(applied) == 2
        assert "0.5 cup white sugar" in modified.ingredients
        assert "2 teaspoons hot water" not in modified.ingredients


class TestMetadataPreservation:
    def test_times_survive_modification(self):
        recipe = make_recipe()
        m = RecipeModifier()
        change = mod(
            "removal",
            [
                ModificationEdit(
                    target="ingredients",
                    operation="remove",
                    find="2 teaspoons hot water",
                )
            ],
        )
        modified, _ = m.apply_modifications(recipe, [(change, review())])
        assert modified.prep_time == "20 mins"
        assert modified.cook_time == "10 mins"
        assert modified.total_time == "30 mins"


class TestChangeRecordIntegrity:
    def test_every_record_is_a_real_diff(self):
        recipe = make_recipe()
        m = RecipeModifier()
        changes = [
            (
                mod(
                    "quantity_adjustment",
                    [
                        ModificationEdit(
                            target="ingredients",
                            operation="replace",
                            find="1 cup white sugar",
                            replace="0.5 cup white sugar",
                        )
                    ],
                ),
                review("a"),
            ),
            (
                mod(
                    "addition",
                    [
                        ModificationEdit(
                            target="ingredients",
                            operation="add_after",
                            find="2 eggs",
                            add="1 additional egg yolk",
                        )
                    ],
                ),
                review("b"),
            ),
        ]
        modified, applied = m.apply_modifications(recipe, changes)
        for _, _, records in applied:
            for r in records:
                assert r.from_text != r.to_text
                if r.operation == "replace":
                    assert r.from_text in recipe.ingredients + recipe.instructions
                    assert r.to_text in modified.ingredients + modified.instructions
