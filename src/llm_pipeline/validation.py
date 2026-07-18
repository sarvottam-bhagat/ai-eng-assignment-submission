"""
Deterministic validation for extracted modifications.

Runs BEFORE any edit is applied. Rejects modifications that are hypothetical,
vague, malformed, or ungrounded — with an explicit reason — so that only
concrete, community-tested changes reach the recipe and the attribution output.
"""

import re
from dataclasses import dataclass
from typing import Optional

from loguru import logger

from .models import ModificationObject

# Markers of changes the reviewer intends/suggests but did not actually test.
HYPOTHETICAL_PATTERNS = [
    r"\bnext time\b",
    r"\bi (?:will|would|might|may|plan to|want to|am going to)\b",
    r"\bi'(?:ll|d)\b",
    r"\bwould (?:be|probably|likely)\b",
    r"\bconsider\b",
    r"\bmaybe\b",
    r"\btry (?:adding|using)\b",
]

# Vague amount words with no concrete quantity attached.
VAGUE_QUANTITY_PATTERN = re.compile(
    r"\b(?:more|less|extra|lots?|plenty|a (?:bit|little|lot)|some|generous(?:ly)?)\b",
    re.IGNORECASE,
)

# A concrete quantity: a number (or unicode fraction / number word) is present.
CONCRETE_QUANTITY_PATTERN = re.compile(
    r"(?:\d|½|⅓|⅔|¼|¾|⅛|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|"
    r"half|quarter|third|dozen|a few|couple|dash|pinch|splash)\b)",
    re.IGNORECASE,
)


@dataclass
class ValidationResult:
    """Outcome of validating a single modification."""

    is_valid: bool
    reason: Optional[str] = None


def _looks_like_prose(text: str) -> bool:
    """Detect review prose/advice masquerading as a recipe line."""
    lowered = text.strip().lower()
    prose_markers = [
        "next time",
        "i think",
        "i found",
        "you should",
        "i recommend",
        "would recommend",
        "!",
        "?",
    ]
    return any(marker in lowered for marker in prose_markers)


def _new_text_fields(modification: ModificationObject) -> list[str]:
    """Collect all text an edit would insert into the recipe."""
    texts = []
    for edit in modification.edits:
        if edit.operation == "replace" and edit.replace:
            texts.append(edit.replace)
        elif edit.operation == "add_after" and edit.add:
            texts.append(edit.add)
    return texts


def validate_modification(
    modification: ModificationObject, review_text: str
) -> ValidationResult:
    """
    Validate one atomic modification against deterministic business rules.

    Args:
        modification: The extracted modification to validate
        review_text: The source review text (for groundedness checks)

    Returns:
        ValidationResult with is_valid and a rejection reason when invalid.
    """
    # 1. Structural rules: each operation needs its required field
    if not modification.edits:
        return ValidationResult(False, "modification contains no edits")

    for edit in modification.edits:
        if not edit.find or not edit.find.strip():
            return ValidationResult(False, "edit has an empty 'find' target")
        if edit.operation == "replace" and not (edit.replace and edit.replace.strip()):
            return ValidationResult(
                False, f"replace edit for '{edit.find}' has no replacement text"
            )
        if edit.operation == "add_after" and not (edit.add and edit.add.strip()):
            return ValidationResult(
                False, f"add_after edit for '{edit.find}' has no text to add"
            )

    # 2. Inserted text must look like a recipe line, not review prose/advice
    for text in _new_text_fields(modification):
        if _looks_like_prose(text):
            return ValidationResult(
                False, f"inserted text looks like review prose, not a recipe line: '{text}'"
            )

    # 3. Vague quantities: "more broth" with no number anywhere is not executable
    for text in _new_text_fields(modification):
        if VAGUE_QUANTITY_PATTERN.search(text) and not CONCRETE_QUANTITY_PATTERN.search(
            text
        ):
            return ValidationResult(
                False, f"inserted text has a vague amount with no concrete quantity: '{text}'"
            )

    # 4. Hypothetical/untested: the reasoning or the review sentence backing this
    #    change must not be purely a future intention. We check the reasoning text
    #    and, for reviews that ONLY speak hypothetically, reject.
    review_lower = review_text.lower()
    reasoning_lower = (modification.reasoning or "").lower()

    for pattern in HYPOTHETICAL_PATTERNS:
        if re.search(pattern, reasoning_lower):
            return ValidationResult(
                False,
                f"reasoning indicates an untested/future suggestion (matched '{pattern}')",
            )

    # If every sentence in the review that mentions changing something is
    # hypothetical, the modification cannot be community-tested. Heuristic:
    # review contains a hypothetical marker AND no past-tense action verbs.
    has_hypothetical = any(
        re.search(p, review_lower) for p in HYPOTHETICAL_PATTERNS
    )
    PAST_TENSE_ACTIONS = re.compile(
        r"\b(?:added|used|substituted|replaced|omitted|reduced|increased|doubled|"
        r"halved|swapped|baked|cooked|refrigerated|chilled|mixed|put|made it with|"
        r"left out|cut|skipped)\b"
    )
    if has_hypothetical and not PAST_TENSE_ACTIONS.search(review_lower):
        return ValidationResult(
            False, "review only describes future intentions, not tested changes"
        )

    return ValidationResult(True)


def filter_valid_modifications(
    extractions: list[tuple[ModificationObject, "object"]],
) -> list[tuple[ModificationObject, "object"]]:
    """
    Filter (modification, review) pairs down to those passing validation.

    Rejections are logged with their reason.
    """
    valid = []
    for modification, review in extractions:
        result = validate_modification(modification, review.text)
        if result.is_valid:
            valid.append((modification, review))
        else:
            logger.warning(
                f"Rejected {modification.modification_type} modification: {result.reason}"
            )
    logger.info(
        f"Validation: {len(valid)}/{len(extractions)} modifications accepted"
    )
    return valid
