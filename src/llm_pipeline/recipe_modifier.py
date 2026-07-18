"""
Step 2: Recipe Modification

Applies structured modifications to recipes using SAFE, deterministic matching:

- Targets resolve by exact match, then normalized equality, then unique substring.
- A fuzzy similarity score alone can never overwrite a line (no whole-line
  fuzzy fallback — that could corrupt the recipe).
- Duplicate edits (same resolved target + same result) are applied once.
- Conflicting edits (two different modifications changing the same original
  line differently) are resolved deterministically: first in stable review
  order wins, later conflicts are skipped with a log message.
"""

import copy
import re
from typing import Dict, List, Optional, Tuple

from loguru import logger

from .models import (
    ChangeRecord,
    ModificationEdit,
    ModificationObject,
    Recipe,
)


def normalize_line(text: str) -> str:
    """Normalize a recipe line for conservative equality comparison."""
    return re.sub(r"\s+", " ", text.strip().lower().rstrip("."))


class RecipeModifier:
    """Applies structured modifications to recipes with conflict tracking."""

    def __init__(self):
        logger.info("Initialized RecipeModifier (exact/normalized/unique-substring matching)")

    def resolve_target(
        self, target_text: str, candidates: List[str]
    ) -> Tuple[Optional[int], str]:
        """
        Resolve which candidate line an edit targets.

        Resolution order:
        1. Exact match (unique)
        2. Normalized equality (unique)
        3. Substring containment (unique — the find text appears in exactly one line)

        Returns:
            (index, method) — index is None when unresolved or ambiguous.
        """
        if not candidates:
            return None, "no_candidates"

        # 1. Exact
        exact = [i for i, c in enumerate(candidates) if c == target_text]
        if len(exact) == 1:
            return exact[0], "exact"
        if len(exact) > 1:
            return None, "ambiguous_exact"

        # 2. Normalized equality
        norm_target = normalize_line(target_text)
        normalized = [
            i for i, c in enumerate(candidates) if normalize_line(c) == norm_target
        ]
        if len(normalized) == 1:
            return normalized[0], "normalized"
        if len(normalized) > 1:
            return None, "ambiguous_normalized"

        # 3. Unique substring (case-insensitive)
        lowered_target = target_text.strip().lower()
        if lowered_target:
            containing = [
                i for i, c in enumerate(candidates) if lowered_target in c.lower()
            ]
            if len(containing) == 1:
                return containing[0], "substring"
            if len(containing) > 1:
                return None, "ambiguous_substring"

        return None, "not_found"

    def apply_modifications(
        self,
        recipe: Recipe,
        extractions: List[Tuple[ModificationObject, object]],
    ) -> Tuple[Recipe, List[Tuple[ModificationObject, object, List[ChangeRecord]]]]:
        """
        Apply a list of (modification, source_review) pairs to a recipe.

        Edits are applied sequentially in stable order with duplicate collapse
        and first-wins conflict handling against ORIGINAL line provenance.

        Returns:
            (modified_recipe, applied) where applied contains one
            (modification, review, change_records) tuple per modification that
            produced at least one real change.
        """
        modified = Recipe(
            recipe_id=f"{recipe.recipe_id}_modified",
            title=recipe.title,
            ingredients=copy.deepcopy(recipe.ingredients),
            instructions=copy.deepcopy(recipe.instructions),
            description=recipe.description,
            servings=recipe.servings,
            rating=recipe.rating,
            prep_time=recipe.prep_time,
            cook_time=recipe.cook_time,
            total_time=recipe.total_time,
        )

        content = {
            "ingredients": modified.ingredients,
            "instructions": modified.instructions,
        }
        # provenance[target][current_index] = index of modification that changed it
        # (original untouched lines are absent from the map)
        provenance: Dict[str, Dict[int, int]] = {
            "ingredients": {},
            "instructions": {},
        }
        # fingerprints of applied edits for duplicate collapse
        applied_fingerprints = set()

        applied: List[Tuple[ModificationObject, object, List[ChangeRecord]]] = []

        for mod_index, (modification, review) in enumerate(extractions):
            change_records: List[ChangeRecord] = []

            for edit in modification.edits:
                if edit.target not in content:
                    logger.warning(f"Unknown edit target: {edit.target}")
                    continue

                lines = content[edit.target]
                prov = provenance[edit.target]
                record = self._apply_single_edit(
                    edit, lines, prov, mod_index, applied_fingerprints
                )
                if record:
                    change_records.append(record)

            if change_records:
                applied.append((modification, review, change_records))
            else:
                logger.warning(
                    f"Modification '{modification.modification_type}' produced no "
                    f"changes; excluding from attribution"
                )

        modified.ingredients = content["ingredients"]
        modified.instructions = content["instructions"]

        total = sum(len(records) for _, _, records in applied)
        logger.info(
            f"Applied {len(applied)}/{len(extractions)} modifications "
            f"({total} changes)"
        )
        return modified, applied

    def _apply_single_edit(
        self,
        edit: ModificationEdit,
        lines: List[str],
        prov: Dict[int, int],
        mod_index: int,
        applied_fingerprints: set,
    ) -> Optional[ChangeRecord]:
        """Apply one edit in place. Returns a ChangeRecord or None."""
        record_type = "ingredient" if edit.target == "ingredients" else "instruction"

        if edit.operation == "replace":
            index, method = self.resolve_target(edit.find, lines)
            if index is None:
                logger.warning(
                    f"Could not resolve replace target '{edit.find}' ({method})"
                )
                return None

            original_text = lines[index]
            if edit.find in original_text and edit.find != original_text:
                # Replace just the matched portion, keep the rest of the line
                new_text = original_text.replace(edit.find, edit.replace or "")
            elif method in ("exact", "normalized"):
                # The whole line IS the target
                new_text = edit.replace or ""
            else:
                # Substring resolution but find-text not literally present
                # (e.g. case difference): be conservative, skip.
                logger.warning(
                    f"Replace target '{edit.find}' resolved by {method} but is not "
                    f"a literal substring; skipping to avoid corrupting the line"
                )
                return None

            if new_text == original_text:
                logger.warning(f"Replace for '{edit.find}' is a no-op; skipping")
                return None

            fingerprint = (edit.target, "replace", index, normalize_line(new_text))
            if fingerprint in applied_fingerprints:
                logger.info(f"Duplicate replace on line {index}; already applied")
                return None

            if index in prov and prov[index] != mod_index:
                logger.warning(
                    f"CONFLICT: line '{original_text}' already changed by an "
                    f"earlier modification; keeping first change, skipping this one"
                )
                return None

            lines[index] = new_text
            prov[index] = mod_index
            applied_fingerprints.add(fingerprint)
            logger.info(f"Replaced ({method}): '{original_text}' -> '{new_text}'")
            return ChangeRecord(
                type=record_type,
                from_text=original_text,
                to_text=new_text,
                operation="replace",
            )

        elif edit.operation == "add_after":
            if not edit.add:
                return None
            index, method = self.resolve_target(edit.find, lines)
            if index is None:
                logger.warning(
                    f"Could not resolve add_after anchor '{edit.find}' ({method})"
                )
                return None

            # Duplicate addition: same normalized content already present
            norm_add = normalize_line(edit.add)
            if any(normalize_line(line) == norm_add for line in lines):
                logger.info(f"Addition '{edit.add}' already present; skipping duplicate")
                return None

            lines.insert(index + 1, edit.add)
            # Shift provenance indices at/after the insertion point
            shifted = {
                (i + 1 if i > index else i): m for i, m in prov.items()
            }
            prov.clear()
            prov.update(shifted)
            prov[index + 1] = mod_index
            logger.info(f"Added ({method}): '{edit.add}' after '{edit.find}'")
            return ChangeRecord(
                type=record_type,
                from_text="",
                to_text=edit.add,
                operation="add",
            )

        elif edit.operation == "remove":
            index, method = self.resolve_target(edit.find, lines)
            if index is None:
                logger.warning(
                    f"Could not resolve remove target '{edit.find}' ({method})"
                )
                return None

            if index in prov and prov[index] != mod_index:
                logger.warning(
                    f"CONFLICT: line '{lines[index]}' already changed by an earlier "
                    f"modification; skipping removal"
                )
                return None

            removed_text = lines.pop(index)
            # Shift provenance indices after the removal point
            shifted = {}
            for i, m in prov.items():
                if i == index:
                    continue
                shifted[i - 1 if i > index else i] = m
            prov.clear()
            prov.update(shifted)
            logger.info(f"Removed ({method}): '{removed_text}'")
            return ChangeRecord(
                type=record_type,
                from_text=removed_text,
                to_text="",
                operation="remove",
            )

        logger.warning(f"Unknown operation: {edit.operation}")
        return None

    def apply_modification(
        self,
        recipe: Recipe,
        modification: ModificationObject,
    ) -> Tuple[Recipe, List[ChangeRecord]]:
        """
        Apply a single modification (convenience wrapper for tests/tools).
        """
        modified, applied = self.apply_modifications(recipe, [(modification, None)])
        records = applied[0][2] if applied else []
        return modified, records
