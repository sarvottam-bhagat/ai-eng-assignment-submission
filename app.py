"""
Streamlit demo — FIXED pipeline (branch: fix/pipeline-correctness)

Shows the full corrected flow stage by stage:
  1. All modification reviews processed (not one random pick)
  2. Atomic modifications extracted per review
  3. Validation rejections with explicit reasons
  4. Safe application with conflict/duplicate skips
  5. Enhanced recipe with per-change attribution + before/after diff

Run:  uv run streamlit run app.py
"""

import json
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from llm_pipeline.pipeline import LLMAnalysisPipeline  # noqa: E402
from llm_pipeline.validation import validate_modification  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent / "data"

st.set_page_config(page_title="FIXED Pipeline Demo", page_icon="✅", layout="wide")
st.title("✅ FIXED Pipeline — fix/pipeline-correctness")
st.caption(
    "All reviews processed · atomic modifications · validation with reasons · "
    "safe matching · conflict detection · full attribution"
)

recipe_files = sorted(DATA_DIR.glob("recipe_*.json"))
choice = st.selectbox(
    "Recipe chuno:",
    recipe_files,
    format_func=lambda p: p.stem.replace("recipe_", "").replace("-", " "),
)

if st.button("🚀 Run Fixed Pipeline", type="primary"):
    pipeline = LLMAnalysisPipeline()

    recipe_data = pipeline.load_recipe_data(str(choice))
    recipe = pipeline.parse_recipe_data(recipe_data)
    reviews = pipeline.parse_reviews_data(recipe_data)
    mod_reviews = [r for r in reviews if r.has_modification]

    st.header(recipe.title)
    c1, c2, c3 = st.columns(3)
    c1.metric("Total reviews", len(reviews))
    c2.metric("Reviews with modifications", len(mod_reviews))
    c3.metric("Reviews processed", f"{len(mod_reviews)} (ALL)", delta="was: 1 random")

    if not mod_reviews:
        st.error(
            "Is recipe ke liye koi modification reviews scrape nahi hue "
            "(upstream data gap) — pipeline correctly skip karti hai."
        )
        st.stop()

    # ---- Stage 1: Atomic extraction from ALL reviews ----
    st.subheader("Stage 1 — Atomic extraction (har review se saare tweaks)")
    with st.spinner("LLM se har review ke atomic modifications nikal rahe hain..."):
        extractions = pipeline.tweak_extractor.extract_all_modifications(
            reviews, recipe
        )

    by_review = {}
    for mod, rev in extractions:
        by_review.setdefault(rev.text, []).append(mod)
    for rev in mod_reviews:
        mods = by_review.get(rev.text, [])
        with st.expander(
            f"📝 Review → {len(mods)} atomic modification(s): "
            f"\"{rev.text[:90]}...\""
        ):
            st.write(rev.text)
            for m in mods:
                st.markdown(f"- **{m.modification_type}** — {m.reasoning}")
            if not mods:
                st.info(
                    "Koi concrete tested change nahi mila (sirf preference/"
                    "intention tha) — LLM ne empty list return ki. Correct!"
                )

    st.success(f"Total: {len(extractions)} atomic modifications from {len(mod_reviews)} reviews")

    # ---- Stage 2: Validation ----
    st.subheader("Stage 2 — Validation (untested/vague reject)")
    valid = []
    for mod, rev in extractions:
        result = validate_modification(mod, rev.text)
        if result.is_valid:
            valid.append((mod, rev))
        else:
            st.warning(f"❌ REJECTED **{mod.modification_type}** — {result.reason}")
    st.success(f"{len(valid)}/{len(extractions)} modifications accepted")

    # ---- Stage 3: Safe application ----
    st.subheader("Stage 3 — Safe application (conflicts/duplicates skip)")
    if valid:
        modified_recipe, applied = pipeline.recipe_modifier.apply_modifications(
            recipe, valid
        )
        skipped = len(valid) - len(applied)
        if skipped:
            st.info(
                f"⚔️ {skipped} modification(s) skip hue — conflict (do reviews same "
                f"line badal rahe the → pehla jeeta), duplicate, ya target line "
                f"recipe mein nahi mili (guess karne ke bajaye skip)."
            )

        for mod, rev, records in applied:
            with st.expander(
                f"✅ {mod.modification_type} — {len(records)} change(s) | "
                f"source: \"{rev.text[:60]}...\""
            ):
                st.caption(f"Why: {mod.reasoning}")
                for c in records:
                    if c.operation == "replace":
                        st.markdown(f"🔁 `{c.from_text}` → **`{c.to_text}`**")
                    elif c.operation == "add":
                        st.markdown(f"➕ **`{c.to_text}`**")
                    else:
                        st.markdown(f"➖ ~~`{c.from_text}`~~")

        # ---- Stage 4: Before / After ----
        st.subheader("Stage 4 — Before vs After")
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
            st.markdown("**Original ingredients**")
            for i in recipe.ingredients:
                if i in changed_from:
                    st.markdown(f"- 🟡 ~~{i}~~")
                else:
                    st.markdown(f"- {i}")
        with colR:
            st.markdown("**Enhanced ingredients**")
            for i in modified_recipe.ingredients:
                if i in added_to:
                    st.markdown(f"- 🟢 **{i}**")
                else:
                    st.markdown(f"- {i}")

        st.metric(
            "Modifications applied (with attribution)",
            len(applied),
            delta=f"was: max 1 on original code",
        )
        st.caption(
            f"Metadata preserved: prep={modified_recipe.prep_time} · "
            f"cook={modified_recipe.cook_time} · total={modified_recipe.total_time}"
        )
    else:
        st.error(
            "Koi modification validation pass nahi kar payi — is recipe ke reviews "
            "mein koi genuinely tested change nahi hai, isliye enhanced recipe NAHI "
            "banayi jaayegi (original code yahan quantities INVENT kar deta tha!)"
        )
