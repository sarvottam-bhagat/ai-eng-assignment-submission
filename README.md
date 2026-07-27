# Recipe Enhancement Platform

This project turns community-tested AllRecipes review suggestions into an enhanced recipe. It uses an LLM to extract individual recipe changes, validates them with deterministic safety checks, and records the source review for every applied change.

The repository includes a Streamlit demo, the pipeline, sample recipe data, and an offline test suite.

## Requirements

- Python 3.13 or newer
- [uv](https://docs.astral.sh/uv/)
- An OpenAI API key to run the Streamlit app or the live pipeline

## Setup

Run these commands from the repository root.

```powershell
# Install the project and development dependencies
uv sync
```

Create a file named `.env` in the repository root:

```env
OPENAI_API_KEY=your_openai_api_key_here
```

The API key is required only for commands that call OpenAI. The automated test suite runs entirely offline.

## Run the application

Start the interactive Streamlit demo:

```powershell
uv run streamlit run app.py
```

Open the local URL printed by Streamlit. Choose a recipe and select **Run the fixed pipeline** to see:

1. Every review containing a suggested modification
2. The individual changes extracted from each review
3. Validation rejections and their reasons
4. Safe application, duplicate handling, and conflict handling
5. The enhanced recipe alongside the original, with review attribution

## Run the pipeline from the command line

These commands make real OpenAI API calls and require `OPENAI_API_KEY` in `.env`.

```powershell
# Process the chocolate-chip-cookie sample
uv run python src/test_pipeline.py single

# Process every sample recipe that has review data
uv run python src/test_pipeline.py all
```

Enhanced recipes and the batch summary are written to `data/enhanced/`, regardless of the directory from which the command is run. Running the live pipeline can update the tracked sample output files in that directory.

## Run tests

Run the deterministic offline test suite (no API key or network access required):

```powershell
uv run pytest
```

## Optional: refresh the source data

The repository already includes sample recipe data. To scrape it again:

```powershell
uv run python src/scraper_v2.py
```

## What was fixed

The original implementation could generate unreliable recipes: it selected one modification review at random, treated a whole review as one change, and applied LLM output without enough safety checks. The following fixes are now in place:

| Area | Before | Now |
| --- | --- | --- |
| Review coverage | One random flagged review was processed | All flagged reviews are processed in a stable order |
| Changes per review | One review was forced into one modification | Reviews can yield multiple atomic, separately attributed modifications |
| Unsafe suggestions | Untested, vague, or malformed suggestions could be applied | Deterministic validation rejects hypothetical, vague, prose-like, and incomplete changes with a reason |
| Recipe matching | Fuzzy matching could target the wrong line or report a change that did not occur | Matching uses exact, normalized, then unique-substring resolution; ambiguous or missing targets are skipped |
| Conflicts and duplicates | Later changes could silently overwrite earlier ones | Conflicts use a deterministic first-wins policy; duplicate additions are applied once |
| Attribution | A change record could exist even when no recipe text changed | Records are written only for verified changes and retain the source review |
| Recipe metadata | Prep, cook, and total times were dropped | Source timing metadata is preserved |
| Output location | Output depended on the current working directory | Output is always anchored to `data/enhanced/` at the repository root |
| Quality checks | No offline regression suite | Offline pytest coverage verifies extraction parsing, validation, matching safety, conflicts, duplicates, attribution, metadata, and summaries |

The system intentionally produces no enhanced recipe when the available reviews contain no concrete, tested modification. It also skips recipes with no scraped reviews instead of inventing changes.

## Project layout

```text
app.py                  Streamlit demonstration UI
src/llm_pipeline/       Extraction, validation, recipe editing, and output generation
src/test_pipeline.py    Live single-recipe and batch pipeline runner
tests/                  Offline regression tests
data/                   Input recipes and generated enhanced recipes
data/enhanced/          Generated recipe JSON and batch summary report
```

For the detailed engineering analysis, validation rationale, and known limitations, see [ANALYSIS.md](ANALYSIS.md).
