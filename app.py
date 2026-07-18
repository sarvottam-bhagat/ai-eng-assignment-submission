"""
Streamlit demo — ORIGINAL pipeline (branch: main, as inherited from GitHub)

Demonstrates the original behavior and its problems:
  - Picks ONE RANDOM review per recipe; every other community tweak is discarded
  - No validation: untested "next time I will..." suggestions and vague amounts
    get applied, sometimes with invented quantities
  - Run it twice: you get a DIFFERENT result each time (random.choice)

Run:  uv run streamlit run app.py
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from llm_pipeline.pipeline import LLMAnalysisPipeline  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent / "data"

st.set_page_config(page_title="ORIGINAL Pipeline Demo", page_icon="⚠️", layout="wide")
st.title("⚠️ ORIGINAL Pipeline — main (as inherited)")
st.caption(
    "One random review per recipe · no validation · results change every run"
)

recipe_files = sorted(DATA_DIR.glob("recipe_*.json"))
choice = st.selectbox(
    "Recipe chuno:",
    recipe_files,
    format_func=lambda p: p.stem.replace("recipe_", "").replace("-", " "),
)

if st.button("🎲 Run Original Pipeline", type="primary"):
    pipeline = LLMAnalysisPipeline()

    recipe_data = pipeline.load_recipe_data(str(choice))
    recipe = pipeline.parse_recipe_data(recipe_data)
    reviews = pipeline.parse_reviews_data(recipe_data)
    mod_reviews = [r for r in reviews if r.has_modification]

    st.header(recipe.title)
    c1, c2, c3 = st.columns(3)
    c1.metric("Total reviews", len(reviews))
    c2.metric("Reviews with modifications", len(mod_reviews))
    c3.metric("Reviews actually used", "1 (random!)" if mod_reviews else "0")

    if not mod_reviews:
        st.error("No modification reviews scraped for this recipe.")
        st.stop()

    if len(mod_reviews) > 1:
        st.warning(
            f"🚨 PROBLEM #1: {len(mod_reviews)} reviews mein community tweaks hain, "
            f"lekin original code sirf **1 RANDOM** review uthata hai — baaki "
            f"{len(mod_reviews) - 1} reviews ke saare tweaks **discard** ho jaate "
            f"hain. Dobara run karo — alag review uthega, alag result aayega!"
        )

    with st.spinner("LLM se ek (random) review ka modification nikal rahe hain..."):
        modification, source_review = (
            pipeline.tweak_extractor.extract_single_modification(reviews, recipe)
        )

    if not modification:
        st.error("Extraction failed for the randomly selected review.")
        st.stop()

    st.subheader("🎲 Randomly selected review")
    st.info(source_review.text)

    st.subheader(f"Extracted: 1 modification ({modification.modification_type})")
    st.warning(
        "🚨 PROBLEM #2: Agar is ek review mein bhi 4-5 alag tweaks hain "
        "(sugar + water + cream of tartar + refrigeration), sab ek hi "
        "modification_type label ke neeche flatten ho jaate hain."
    )
    st.caption(f"Reasoning: {modification.reasoning}")
    for e in modification.edits:
        st.markdown(
            f"- `{e.operation}` on **{e.target}**: find `{e.find}`"
            + (f" → `{e.replace}`" if e.replace else "")
            + (f" + add `{e.add}`" if e.add else "")
        )

    modified_recipe, change_records = pipeline.recipe_modifier.apply_modification(
        recipe, modification
    )

    st.subheader("Applied changes")
    st.warning(
        "🚨 PROBLEM #3: Koi validation nahi hai — 'next time I will...' jaise "
        "UNTESTED suggestions bhi apply ho jaate hain, aur vague amounts "
        "('use more broth') ke liye LLM quantities INVENT kar deta hai. "
        "Sweet-potato-soup pe run karke dekho — kabhi-kabhi "
        "'Use more broth next time.' literally INGREDIENT ban jaata hai!"
    )
    for c in change_records:
        if c.operation == "replace":
            st.markdown(f"🔁 `{c.from_text}` → `{c.to_text}`")
        elif c.operation == "add":
            st.markdown(f"➕ `{c.to_text}`")
        else:
            st.markdown(f"➖ ~~`{c.from_text}`~~")

    colL, colR = st.columns(2)
    with colL:
        st.markdown("**Original ingredients**")
        for i in recipe.ingredients:
            st.markdown(f"- {i}")
    with colR:
        st.markdown("**'Enhanced' ingredients (from 1 random review)**")
        for i in modified_recipe.ingredients:
            st.markdown(f"- {i}")

    st.error(
        f"Final: sirf **1 modification** apply hui, jabki {len(mod_reviews)} "
        f"reviews mein community ke tested tweaks maujood the. "
        f"Metadata bhi kho gaya (prep/cook/total time = null)."
    )
