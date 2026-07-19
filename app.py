"""
Streamlit demo — ORIGINAL pipeline (branch: main, as inherited from GitHub)

Shows how the original code behaves and where it goes wrong:
  - Picks ONE RANDOM review per recipe; every other community tweak is discarded
  - No validation: untested "next time I will..." suggestions and vague amounts
    get applied, sometimes with invented quantities
  - Run it twice: you get a DIFFERENT result each time (random.choice)

Run:  uv run streamlit run app.py
"""

import re
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from llm_pipeline.pipeline import LLMAnalysisPipeline  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent / "data"

st.set_page_config(page_title="Original Pipeline Demo", page_icon="⚠️", layout="wide")

st.title("⚠️ The original pipeline (before fixes)")
st.markdown(
    "**What this app shows:** the recipe-enhancement code exactly as it was "
    "inherited. Pick a recipe, press Run, and watch what it does — and what "
    "it gets wrong."
)

recipe_files = sorted(DATA_DIR.glob("recipe_*.json"))
choice = st.selectbox(
    "Pick a recipe:",
    recipe_files,
    format_func=lambda p: p.stem.replace("recipe_", "").replace("-", " "),
)

if st.button("Run the original pipeline", type="primary", icon="🎲"):
    pipeline = LLMAnalysisPipeline()

    recipe_data = pipeline.load_recipe_data(str(choice))
    recipe = pipeline.parse_recipe_data(recipe_data)
    reviews = pipeline.parse_reviews_data(recipe_data)
    mod_reviews = [r for r in reviews if r.has_modification]

    st.header(recipe.title)

    c1, c2, c3 = st.columns(3)
    c1.metric("Reviews on this recipe", len(reviews))
    c2.metric("Reviews that suggest changes", len(mod_reviews))
    c3.metric("Reviews the code actually uses", "just 1, picked at random" if mod_reviews else "0")

    with st.expander(f"See all {len(reviews)} reviews"):
        for i, r in enumerate(reviews, 1):
            tag = "💡 suggests changes" if r.has_modification else "💬 just a comment"
            st.markdown(f"**Review {i}** — {tag}")
            st.caption(r.text)
            st.divider()

    if not mod_reviews:
        st.error(
            "No reviews with suggestions were collected for this recipe, "
            "so there is nothing to work with."
        )
        st.stop()

    if len(mod_reviews) > 1:
        st.error(
            f"**Problem 1 — most feedback is thrown away.** "
            f"{len(mod_reviews)} people shared changes they made to this recipe, "
            f"but the code picks **only one review, completely at random**, and "
            f"ignores the other {len(mod_reviews) - 1}. Press Run again and you "
            f"will likely get a different review — and a different final recipe.",
            icon="🗑️",
        )

    st.divider()

    # ---------------- STEP 1 ----------------
    st.subheader("Step 1 · The code picks one review — like a lottery")
    st.caption(
        "This step is simple code, not AI. It shuffles the reviews and grabs one at random."
    )

    with st.spinner("Asking the AI to read the selected review..."):
        modification, source_review = (
            pipeline.tweak_extractor.extract_single_modification(reviews, recipe)
        )

    if not modification:
        st.error("The AI could not read anything useful from the selected review.")
        st.stop()

    st.markdown("**🎲 The review that won the lottery this time:**")
    st.info(source_review.text)

    hypothetical = re.search(
        r"\bnext time\b|\bwhen i make it again\b|\bi (?:will|would|might)\b|\bi'(?:ll|d)\b",
        source_review.text.lower(),
    )
    if hypothetical:
        st.error(
            f"**Problem 2 — this suggestion was never actually tried.** Notice the "
            f"words *“{hypothetical.group(0)}”* — the reviewer is talking about "
            f"the **future**. They never actually made this change. The code has "
            f"no way to notice this, so it will apply it anyway.",
            icon="🔮",
        )

    discarded = [r for r in mod_reviews if r.text != source_review.text]
    if discarded:
        with st.expander(
            f"See the {len(discarded)} reviews that were thrown away (the AI never saw these)"
        ):
            for i, r in enumerate(discarded, 1):
                st.markdown(f"**Thrown away #{i}:**")
                st.caption(r.text)
                st.divider()

    st.divider()

    # ---------------- STEP 2 ----------------
    st.subheader("Step 2 · The AI turns that one review into edit instructions")
    st.caption(
        "This is the only place AI is used. It reads the review and answers: "
        "“what change did this person make?” — as find-and-replace instructions."
    )

    n_edits = len(modification.edits)
    st.markdown(
        f"**The AI found {n_edits} edit instruction{'s' if n_edits != 1 else ''} "
        f"in the review:**"
    )
    for e in modification.edits:
        if e.operation == "replace":
            st.markdown(f"- 🔁 Find **“{e.find}”** and replace it with **“{e.replace}”**")
        elif e.operation == "add_after":
            st.markdown(f"- ➕ Add **“{e.add}”** right after **“{e.find}”**")
        else:
            st.markdown(f"- ➖ Remove **“{e.find}”**")
    st.caption(f"AI's explanation: {modification.reasoning}")

    st.warning(
        "**Problem 3 — one label for everything.** Even if the reviewer made "
        "several different changes (less sugar AND extra egg AND chill the "
        "dough), the code forces them all under a single label "
        f"(here: `{modification.modification_type}`). Separate ideas get merged "
        "or lost.",
        icon="🏷️",
    )

    st.divider()

    # ---------------- STEP 3 ----------------
    st.subheader("Step 3 · The code applies the edits — without checking anything")
    st.caption(
        "Simple find-and-replace, no AI, and crucially: **no safety checks at all**."
    )

    modified_recipe, change_records = pipeline.recipe_modifier.apply_modification(
        recipe, modification
    )

    if not change_records:
        st.error(
            "The edit instructions did not match anything in the recipe, so "
            "nothing was changed — yet the code would still count this as a success."
        )
        st.stop()

    # Dynamic checks on what actually got applied in THIS run
    problems_this_run = []
    if hypothetical:
        problems_this_run.append(
            "An idea the reviewer **never actually tried** (see Step 1) was "
            "applied to the recipe as if it were tested advice."
        )
    for c in change_records:
        inserted = c.to_text.lower()
        if re.search(r"\bnext time\b|\bi (?:will|would)\b|\badded a\b|\band added\b", inserted):
            problems_this_run.append(
                f"A **sentence from the review** ended up inside the recipe as if "
                f"it were an ingredient: *“{c.to_text}”*"
            )
        elif re.search(r"\b(?:more|less|extra|some|lots of)\b", inserted) and not re.search(
            r"\d|half|quarter", inserted
        ):
            problems_this_run.append(
                f"A **vague amount with no real quantity** was added: *“{c.to_text}”*"
            )

    st.markdown("**Changes made to the recipe:**")
    for c in change_records:
        if c.operation == "replace":
            st.markdown(f"- 🔁 “{c.from_text}” → **“{c.to_text}”**")
        elif c.operation == "add":
            st.markdown(f"- ➕ **“{c.to_text}”**")
        else:
            st.markdown(f"- ➖ ~~“{c.from_text}”~~")

    if problems_this_run:
        st.error(
            "**Problems caught in this very run:**\n\n"
            + "\n".join(f"- {p}" for p in problems_this_run),
            icon="🚨",
        )
    else:
        st.info(
            "This particular change happens to look fine — **but that is luck, "
            "not design**. There are zero checks in the code. Run it again with "
            "another recipe and broken changes go straight in.",
            icon="🍀",
        )

    st.divider()

    # ---------------- RESULT ----------------
    st.subheader("The result, side by side")
    colL, colR = st.columns(2)

    changed_from = {c.from_text for c in change_records if c.from_text}
    added_to = {c.to_text for c in change_records if c.to_text}

    with colL:
        st.markdown("#### Original recipe")
        for i in recipe.ingredients:
            if i in changed_from:
                st.markdown(f"- 🟡 ~~{i}~~")
            else:
                st.markdown(f"- {i}")
    with colR:
        st.markdown("#### “Enhanced” recipe")
        for i in modified_recipe.ingredients:
            if i in added_to:
                st.markdown(f"- 🟢 **{i}**")
            else:
                st.markdown(f"- {i}")

    st.divider()
    st.markdown("### The bottom line")
    st.error(
        f"Out of **{len(mod_reviews)} reviews full of community suggestions**, this "
        f"run used **1 randomly-picked review** and made "
        f"**{len(change_records)} change{'s' if len(change_records) != 1 else ''}**. "
        f"Everything else was thrown away — and nothing that was applied was "
        f"ever checked. Press **Run** again: you will probably get a different "
        f"answer from the same data.",
        icon="📉",
    )
