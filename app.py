"""
Streamlit demo — FIXED pipeline (branch: fix/pipeline-correctness)

Shows the corrected flow, stage by stage:
  1. ALL modification reviews processed (not one random pick)
  2. Multiple atomic modifications extracted per review
  3. Validation rejections with explicit reasons
  4. Safe application with conflict/duplicate skips
  5. Enhanced recipe with per-change attribution + before/after diff

Run:  uv run streamlit run app.py
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from llm_pipeline.pipeline import LLMAnalysisPipeline  # noqa: E402
from llm_pipeline.validation import validate_modification  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent / "data"

st.set_page_config(page_title="Fixed Pipeline Demo", page_icon="✅", layout="wide")

st.title("✅ The fixed pipeline")
st.markdown(
    "**What this app shows:** the same recipe-enhancement task, after the fixes. "
    "Every review is read, every suggestion is checked, and only safe, "
    "genuinely-tested changes make it into the final recipe — each one with "
    "credit to the reviewer who suggested it."
)

recipe_files = sorted(DATA_DIR.glob("recipe_*.json"))
choice = st.selectbox(
    "Pick a recipe:",
    recipe_files,
    format_func=lambda p: p.stem.replace("recipe_", "").replace("-", " "),
)

if st.button("Run the fixed pipeline", type="primary", icon="🚀"):
    pipeline = LLMAnalysisPipeline()

    recipe_data = pipeline.load_recipe_data(str(choice))
    recipe = pipeline.parse_recipe_data(recipe_data)
    reviews = pipeline.parse_reviews_data(recipe_data)
    mod_reviews = [r for r in reviews if r.has_modification]

    st.header(recipe.title)

    c1, c2, c3 = st.columns(3)
    c1.metric("Reviews on this recipe", len(reviews))
    c2.metric("Reviews that suggest changes", len(mod_reviews))
    c3.metric(
        "Reviews the code uses",
        f"all {len(mod_reviews)}" if mod_reviews else "0",
        delta="original code used just 1, at random",
    )

    with st.expander(f"See all {len(reviews)} reviews"):
        for i, r in enumerate(reviews, 1):
            tag = "💡 suggests changes" if r.has_modification else "💬 just a comment"
            st.markdown(f"**Review {i}** — {tag}")
            st.caption(r.text)
            st.divider()

    if not mod_reviews:
        st.error(
            "No reviews with suggestions were collected for this recipe "
            "(a data-collection gap), so the pipeline correctly skips it "
            "instead of inventing changes."
        )
        st.stop()

    st.divider()

    # ---------------- STEP 1 ----------------
    st.subheader("Step 1 · The AI reads EVERY review and lists each change separately")
    st.caption(
        "One review often contains several different ideas — less sugar AND an "
        "extra egg AND chill the dough. Each idea becomes its own separate entry."
    )

    with st.spinner("The AI is reading every review..."):
        extractions = pipeline.tweak_extractor.extract_all_modifications(
            reviews, recipe
        )

    by_review = {}
    for mod, rev in extractions:
        by_review.setdefault(rev.text, []).append(mod)

    for i, rev in enumerate(mod_reviews, 1):
        mods = by_review.get(rev.text, [])
        n = len(mods)
        with st.expander(
            f"Review {i} → {n} change idea{'s' if n != 1 else ''} found"
        ):
            st.info(rev.text)
            for m in mods:
                st.markdown(f"- **{m.modification_type.replace('_', ' ')}** — {m.reasoning}")
            if not mods:
                st.warning(
                    "No genuinely-tested change found here — the reviewer only "
                    "shared a preference or a future plan, so the AI correctly "
                    "returned nothing."
                )

    st.success(
        f"**{len(extractions)} separate change ideas** found across "
        f"{len(mod_reviews)} reviews. The original code would have kept "
        f"only one idea from one random review."
    )

    st.divider()

    # ---------------- STEP 2 ----------------
    st.subheader("Step 2 · Every idea is checked before it can touch the recipe")
    st.caption(
        "Ideas that were never actually tried (“next time I will...”), vague "
        "amounts with no real quantity (“use more broth”), or review sentences "
        "pretending to be ingredients — all get rejected, with the reason shown."
    )

    valid = []
    rejected_count = 0
    for mod, rev in extractions:
        result = validate_modification(mod, rev.text)
        if result.is_valid:
            valid.append((mod, rev))
        else:
            rejected_count += 1
            st.error(
                f"**Rejected:** {mod.modification_type.replace('_', ' ')} — {result.reason}",
                icon="🛑",
            )

    if rejected_count == 0:
        st.success(
            f"All {len(extractions)} ideas passed the checks — every reviewer "
            f"here described changes they actually made."
        )
    else:
        st.success(
            f"{len(valid)} of {len(extractions)} ideas passed the checks. "
            f"{rejected_count} unsafe idea{'s were' if rejected_count != 1 else ' was'} "
            f"kept out of the recipe."
        )

    st.divider()

    # ---------------- STEP 3 ----------------
    st.subheader("Step 3 · Safe ideas are applied — carefully")
    st.caption(
        "If two reviewers change the same line differently, the first one wins and "
        "the clash is logged. Duplicates are applied only once. If an instruction "
        "doesn't match the recipe text, it is skipped rather than guessed."
    )

    if not valid:
        st.error(
            "No idea survived the checks — the reviews for this recipe contain "
            "no genuinely tested changes, so **no enhanced recipe is produced**. "
            "(The original code would have invented one anyway.)"
        )
        st.stop()

    modified_recipe, applied = pipeline.recipe_modifier.apply_modifications(
        recipe, valid
    )
    skipped = len(valid) - len(applied)
    if skipped:
        st.info(
            f"{skipped} idea{'s were' if skipped != 1 else ' was'} skipped on "
            f"purpose — a clash with an earlier change, an exact duplicate, or "
            f"an instruction that didn't match the recipe text. Skipping is the "
            f"safe choice; guessing is how recipes get corrupted.",
            icon="⚖️",
        )

    st.markdown("**Changes that made it in — each credited to its reviewer:**")
    for mod, rev, records in applied:
        n = len(records)
        with st.expander(
            f"✅ {mod.modification_type.replace('_', ' ')} — {n} change{'s' if n != 1 else ''} "
            f"· from: “{rev.text[:60]}...”"
        ):
            st.caption(f"Why: {mod.reasoning}")
            for c in records:
                if c.operation == "replace":
                    st.markdown(f"- 🔁 “{c.from_text}” → **“{c.to_text}”**")
                elif c.operation == "add":
                    st.markdown(f"- ➕ **“{c.to_text}”**")
                else:
                    st.markdown(f"- ➖ ~~“{c.from_text}”~~")

    st.divider()

    # ---------------- RESULT ----------------
    st.subheader("The result, side by side")
    colL, colR = st.columns(2)

    changed_from = set()
    added_to = set()
    for _, _, records in applied:
        for c in records:
            if c.from_text:
                changed_from.add(c.from_text)
            if c.to_text:
                added_to.add(c.to_text)

    with colL:
        st.markdown("#### Original recipe")
        for i in recipe.ingredients:
            if i in changed_from:
                st.markdown(f"- 🟡 ~~{i}~~")
            else:
                st.markdown(f"- {i}")
    with colR:
        st.markdown("#### Enhanced recipe")
        for i in modified_recipe.ingredients:
            if i in added_to:
                st.markdown(f"- 🟢 **{i}**")
            else:
                st.markdown(f"- {i}")

    st.divider()
    st.markdown("### The bottom line")
    total_changes = sum(len(records) for _, _, records in applied)
    st.success(
        f"**{len(applied)} community improvements applied** "
        f"({total_changes} individual changes), drawn from all "
        f"{len(mod_reviews)} reviews — every change checked, every change "
        f"credited to its reviewer, and the recipe's timing info "
        f"(prep {modified_recipe.prep_time or '—'} · cook "
        f"{modified_recipe.cook_time or '—'} · total "
        f"{modified_recipe.total_time or '—'}) preserved. The original code "
        f"managed at most 1 unchecked change from 1 random review.",
        icon="🏆",
    )
