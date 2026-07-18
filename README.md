# Recipe Enhancement Platform

Automatically enhances recipes by analyzing and applying community-tested modifications from AllRecipes.com. Uses LLM processing to extract meaningful recipe tweaks and apply them with full citation tracking.

## Installation

This project uses [`uv`](https://docs.astral.sh/uv/) for fast, reliable Python package management.

### Prerequisites

- Python 3.13+
- `uv` package manager

## Setup

```bash
# Install dependencies
uv venv
source .venv/bin/activate
uv pip sync pyproject.toml
```

### Environment Variables

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=your-openai-api-key-here
```

## Usage

### 1. Scrape Recipes (Optional - data already provided)

```bash
uv run python src/scraper_v2.py
```

### 2. Run Recipe Enhancement Pipeline

```bash
# Works from any directory — paths are anchored to the repo root
cd src

# Test single recipe (chocolate chip cookies)
uv run python test_pipeline.py single

# Process all recipes
uv run python test_pipeline.py all
```

## Output

### Enhanced Recipes

Enhanced recipes are saved in `data/enhanced/` (at the repo root):

- `enhanced_[recipe_id]_[recipe-name].json` - Individual enhanced recipes with modifications applied
- `pipeline_summary_report.json` - Summary of all processing results

### Data Structure

Original scraped recipes in `data/` directory contain reviews with `has_modification: true` flags. Enhanced recipes include:

```json
{
  "recipe_id": "10813_enhanced",
  "title": "Best Chocolate Chip Cookies (Community Enhanced)",
  "ingredients": ["1 cup butter", "1 additional egg yolk", ...],
  "modifications_applied": [
    {
      "source_review": {
        "text": "I added an extra egg yolk for chewier texture",
        "rating": 5
      },
      "modification_type": "addition",
      "reasoning": "Improves texture and chewiness",
      "changes_made": [...]
    }
  ],
  "enhancement_summary": {
    "total_changes": 1,
    "change_types": ["addition"],
    "expected_impact": "Chewier texture and improved consistency"
  }
}
```

## How It Works

The LLM Analysis Pipeline processes recipes in 3 steps:

1. **Tweak Extraction**: Processes **every** review flagged with modifications; GPT-4o-mini extracts a **list of atomic modifications** per review (one review saying "added an egg and halved sugar" yields two separate attributed tweaks)
2. **Validation**: Deterministic rules reject untested suggestions ("next time I will…"), vague amounts ("use more broth"), and prose masquerading as recipe lines — before anything touches the recipe
3. **Recipe Modification**: Applies validated changes with safe matching (exact → normalized → unique substring; never fuzzy overwrites), duplicate collapse, and first-wins conflict detection
4. **Enhanced Recipe Generation**: Creates the enhanced version with one citation per atomic modification, tracking back to the source review

Each run produces one enhanced recipe per eligible original recipe. A recipe whose reviews contain no genuinely tested change correctly produces no output.

## Testing

```bash
# Offline unit tests — no API key needed
uv run pytest
```

See [`ANALYSIS.md`](ANALYSIS.md) for the full write-up: original failure modes, fixes, verification, and future improvements.

## Development

```bash
# Add dependencies
uv add <package_name>

# Run tests
cd src && uv run python test_pipeline.py single
```
