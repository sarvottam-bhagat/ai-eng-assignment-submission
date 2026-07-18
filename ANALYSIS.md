# Analysis Document — Recipe Enhancement Pipeline

**Casper Studios Take Home Assessment — AI Engineer**

This document compares the **original GitHub implementation** (as inherited, commit `bcd62cf` lineage) with the final fixed implementation: what the product was supposed to do, exactly how the original failed, what I changed, and how I verified it.

---

## 1. Product Intent & Assumptions

**Intent**: AllRecipes reviews contain community-tested recipe tweaks ("I added an extra egg yolk", "I halved the sugar"). The pipeline should produce an *Enhanced Recipe* — the original with those tested tweaks applied — where every changed line is attributed back to the specific review that suggested it, so a UI can show line-level diffs with citations.

**Assumptions I worked under:**

- "Added an egg and halved the sugar" is **two discrete modifications**, each needing its own type, reasoning, and attribution — the assignment brief calls this out explicitly.
- Only changes a reviewer **actually made and tested** qualify as "community-tested". Future intentions ("next time I will…"), preferences ("I would prefer…"), and vague suggestions with no amounts ("use more broth") must not silently become recipe lines.
- The enhanced recipe must remain a *valid recipe*: no review prose in the ingredient list, no invented quantities the reviewer never stated, no lines corrupted by bad matching.
- Two recipes in `data/` have `"reviews": []` (nothing was scraped) — that is an upstream data gap, not a pipeline bug; the pipeline should skip them loudly, not crash or fake output.

## 2. What Was Broken in the Original Implementation

Diagnosed by reading every module, then running the original pipeline against all six sample recipes.

### 2.1 Only one random review was ever processed (critical)

`TweakExtractor.extract_single_modification()` filtered reviews to `has_modification=True`, then did `random.choice()` — one review picked at random, one `ModificationObject` extracted from it, everything else discarded, different answer every run.

**Evidence**: the sweet-potato-soup recipe has 5 modification reviews; the original run used exactly 1 (`ground ginger → fresh ginger`) and dropped the other 4. The repo even contained unused scaffolding (`apply_modifications_batch`, `validate_modification_safety`, list-typed `modifications_applied`) for the multi-modification design that was never wired in.

### 2.2 One review = one modification, even when it bundles several (critical — the assignment's explicit hint)

The schema forced a single `modification_type` per review. The best cookie review bundles **four** distinct tweaks (sugar-ratio change, water removal, cream-of-tartar addition, dough refrigeration); the original flattened whichever subset the LLM happened to emit under one label, and typically lost most of them.

### 2.3 No validation — untested and vague suggestions became recipe lines (critical)

The original applied whatever the LLM emitted. Observed real failures:

- `"Use more broth next time."` — review prose — inserted verbatim as a soup **ingredient**.
- A reviewer said only "I would prefer some more apple chunks" (a preference, never tested); the pipeline **invented** a quantity (`3 cups apple`) and applied it.
- "Next time I will use fresh ginger" (untested intention) was applied as if tested.

### 2.4 Unsafe fuzzy matching could corrupt lines or record fake changes

`apply_edit` fuzzy-matched a line (similarity ≥ 0.6) and then ran an exact `str.replace` on it. Two failure modes: (a) if the `find` text wasn't literally in the matched line, the replace silently did nothing while a "successful" `ChangeRecord` was still written — the attribution data lied; (b) a similar-but-different line could be targeted. `remove` popped an entire line even when the edit meant a substring.

### 2.5 Conflicts silently overwrote each other

Nothing detected two reviews editing the same line differently — last writer won, invisibly.

### 2.6 Supporting defects

- Output path depended on the working directory: following the README split outputs across `data/enhanced/` and `src/data/enhanced/`.
- Source metadata (`preptime`/`cooktime`/`totaltime`) was silently dropped — all enhanced outputs had `null` times.
- README claimed GPT-4o-mini; code used `gpt-3.5-turbo`.
- `test_pipeline.py all` "passed" if even 1 of 6 recipes produced output; no automated tests existed at all.
- The checked-in example output (`confidence_score` fields, 2 modifications) was not reproducible by the checked-in code — it came from an older version.

## 3. Technical Decisions

- **Atomic extraction, per review**: the LLM now returns `{"modifications": [...]}` — a list of atomic `ModificationObject`s per review — with strict prompt rules (tested-only, no invented quantities, exact source text for `find`, empty list when nothing qualifies). One LLM call per review keeps failures isolated; parsing is a pure function (`parse_extraction_response`) so it is unit-testable offline, and it still accepts the legacy single-object shape defensively.
- **Deterministic validation, separate from the LLM** (`validation.py`): business rules — not another model call — reject modifications that are hypothetical (regex markers like "next time", "I would" without any past-tense action in the review), vague ("more broth" with no number), prose-as-ingredient, or structurally incomplete (replace without replacement, etc.). Every rejection logs a reason. The LLM proposes; deterministic code disposes.
- **Safe matching, no fuzzy overwrites** (`recipe_modifier.py` rewrite): targets resolve by exact match → normalized equality → unique substring, in that order; ambiguous or missing targets are skipped, never guessed. A similarity score alone can never replace a line. Change records are only written for real diffs.
- **First-wins conflict handling + duplicate collapse**: edits carry provenance per original line; a later modification touching an already-changed line is skipped with a `CONFLICT` log (deterministic, stable review order) instead of silently overwriting. Identical additions from different reviews apply once. First-wins is a deliberate MVP choice — ranking by review helpfulness is future work.
- **Offline test suite over live smoke runs**: 31 pytest tests cover extraction parsing (bundled review → 4 atomic modifications), every validation rule, matcher safety (the fuzzy-corruption case is a regression test), conflicts/duplicates, metadata preservation, and summary integrity — all deterministic, no API key needed. The live `test_pipeline.py` remains for regenerating sample outputs, and its "all" mode now fails unless (eligible − 1) recipes succeed instead of just 1.
- **Kept the 3-stage architecture**: the design (extract → apply → attribute) was sound; the defects were in the logic. A rewrite would have destroyed the reviewability of the diff.

## 4. Implementation Summary

| Area | Original | Fixed |
|---|---|---|
| Review coverage | 1 random review | All flagged reviews, deduplicated, stable order |
| Modifications per review | Exactly 1 | List of atomic modifications (`ExtractionResponse`) |
| Untested/vague suggestions | Applied, sometimes with invented amounts | Rejected pre-application with logged reasons |
| Matching | Fuzzy ≥ 0.6 then blind `str.replace` (silent no-ops, possible corruption) | Exact → normalized → unique-substring; ambiguous = skip |
| Conflicts | Silent last-writer-wins | Detected via line provenance; first-wins + log |
| Duplicates | Could apply twice | Fingerprint + normalized-content collapse |
| Attribution | Could record changes that never happened | Every `ChangeRecord` is a verified real diff |
| Metadata | Times dropped (`null`) | `preptime/cooktime/totaltime` mapped through |
| Output path | Depended on CWD | Anchored to repo root |
| Model | `gpt-3.5-turbo` (README said otherwise) | `gpt-4o-mini` |
| Tests | None (smoke script passing on 1/6) | 31 offline pytest tests + honest batch criteria |

Files: `models.py` (+`ExtractionResponse`, time fields), `prompts.py` (atomic-list prompt with strict rules), `tweak_extractor.py` (multi-extraction + pure parser), `validation.py` (new), `recipe_modifier.py` (rewritten), `pipeline.py` (extract → validate → apply wiring, root-anchored paths, per-modification report counts), `enhanced_recipe_generator.py` (multi-attribution, deterministic ordering), `test_pipeline.py`, `tests/` (new), `README.md`.

## 5. Verified Results

`uv run pytest` → **31/31 passing, offline.** Live regeneration across all six recipes:

| Recipe | Original output | Fixed output |
|---|---|---|
| Chocolate chip cookies (4 mod-reviews) | 1 modification | **12 atomic extracted → 8 applied, 9 changes** (sugar ratio, egg yolk, water removal, cream of tartar, salt, walnut removal, flour reduction, scooping technique); 4 skipped as conflicts/duplicates — e.g. two reviews both changing the sugar lines resolve first-wins instead of overwriting |
| Sweet potato soup (5 mod-reviews) | 1 modification | **12 extracted → 3 rejected by validation** ("next time fresh ginger" = untested; `"Use more broth…"` prose; "lots of black pepper" vague) **→ 6 applied** |
| Nikujaga | 1 modification | 3 atomic (meat quantity + soy + sugar from one bundled review) |
| Spicy apple cake | Applied an **invented** `3 cups apple` from an untested preference | **Correctly produces no output** — both reviews are hypothetical/preference-only; nothing community-tested to apply |
| Plum jam, mango marinade | Skipped (no review data) | Same, with clear logging — upstream scraper gap |

The apple-cake row is the clearest behavior change: the original fabricated a change to have something to show; the fixed pipeline refuses, because a recipe enhanced with untested guesses is worse than the original recipe.

## 6. Remaining Limitations & Future Improvements

1. **Validation is heuristic**: regex markers for hypothetical/vague language have edge cases (e.g. "lots of black pepper" slipped through as an *applied* line in one soup review where the reviewer genuinely used it — tightened, but a tested-vs-vague judgment sometimes needs semantics, not regex). A small LLM-as-judge pass with a golden eval set is the next step.
2. **First-wins conflict policy is crude**: with helpfulness votes/ratings scraped, conflicts should resolve by community signal, or surface as alternatives in the UI.
3. **Scale**: one call per review is fine at ~5 reviews/recipe but not at thousands of recipes × hundreds of reviews. The design pushes selection upstream (featured/top-N reviews first, `featured_tweaks` already exist in the data); batching and caching come next.
4. **Extraction recall is unmeasured**: tests prove parsing/validation/application correctness, but "did the LLM find every tweak in the review?" needs a labeled golden set of review → expected-modifications pairs.
5. **Scraper gaps**: two recipes lack reviews entirely; no reviewer usernames are scraped, so attribution shows `reviewer: null`.
6. **Structured outputs**: moving to OpenAI structured-output mode with the Pydantic schema would remove the JSON-retry path.
7. **UI surface**: `generate_comparison_data()` produces the diff+citation structure the product needs but nothing consumes it yet.
