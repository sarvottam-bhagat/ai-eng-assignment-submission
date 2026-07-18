"""
Step 1: Tweak Extraction & Parsing

This module extracts structured modifications from review text using LLM processing.
One review can contain several distinct tweaks, so extraction returns a LIST of
atomic ModificationObject instances per review.
"""

import json
import os
from typing import Optional

from loguru import logger
from openai import OpenAI
from pydantic import ValidationError

from .models import ExtractionResponse, ModificationObject, Recipe, Review
from .prompts import build_simple_prompt


class TweakExtractor:
    """Extracts structured modifications from review text using LLM processing."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        """
        Initialize the TweakExtractor.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: OpenAI model to use for extraction
        """
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.model = model
        logger.info(f"Initialized TweakExtractor with model: {model}")

    def extract_modifications(
        self,
        review: Review,
        recipe: Recipe,
        max_retries: int = 2,
    ) -> list[ModificationObject]:
        """
        Extract ALL atomic modifications from a single review.

        Args:
            review: Review object containing modification text
            recipe: Original recipe being modified
            max_retries: Number of retry attempts if parsing fails

        Returns:
            List of atomic ModificationObject instances (may be empty when the
            review contains no concrete tested change).
        """
        if not review.has_modification:
            logger.warning("Review has no modification flag set")
            return []

        prompt = build_simple_prompt(
            review.text, recipe.title, recipe.ingredients, recipe.instructions
        )

        logger.debug(
            "Extracting modifications from review: {}...".format(review.text[:100])
        )

        raw_output = None
        for attempt in range(max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.1,  # Low temperature for consistent extractions
                    max_tokens=2000,
                )

                raw_output = response.choices[0].message.content
                logger.debug(f"LLM raw output: {raw_output}")

                if not raw_output:
                    logger.warning(f"Attempt {attempt + 1}: Empty response from LLM")
                    continue

                extraction = self.parse_extraction_response(raw_output)

                logger.info(
                    f"Extracted {len(extraction.modifications)} atomic "
                    f"modification(s) from review"
                )
                return extraction.modifications

            except json.JSONDecodeError as e:
                logger.warning(f"Attempt {attempt + 1}: Failed to parse JSON: {e}")
                if attempt == max_retries:
                    logger.error(f"Max retries reached. Raw output: {raw_output}")

            except ValidationError as e:
                logger.warning(f"Attempt {attempt + 1}: Validation error: {e}")
                if attempt == max_retries:
                    logger.error(f"Max retries reached. Raw output: {raw_output}")

            except Exception as e:
                logger.error(f"Attempt {attempt + 1}: Unexpected error: {e}")
                if attempt == max_retries:
                    return []

        return []

    @staticmethod
    def parse_extraction_response(raw_output: str) -> ExtractionResponse:
        """
        Parse and validate a raw LLM JSON response into an ExtractionResponse.

        Accepts both the current wrapper format {"modifications": [...]} and a
        bare single-modification object (legacy format) for robustness.

        Raises:
            json.JSONDecodeError / pydantic.ValidationError on malformed input.
        """
        data = json.loads(raw_output)

        if isinstance(data, dict) and "modifications" in data:
            return ExtractionResponse(**data)

        # Legacy single-object response: wrap it
        return ExtractionResponse(modifications=[ModificationObject(**data)])

    def extract_all_modifications(
        self, reviews: list[Review], recipe: Recipe
    ) -> list[tuple[ModificationObject, Review]]:
        """
        Extract atomic modifications from ALL reviews flagged with modifications.

        Args:
            reviews: List of reviews to process
            recipe: Original recipe being modified

        Returns:
            Flat list of (ModificationObject, source_Review) pairs in stable
            review order. Empty list if nothing could be extracted.
        """
        modification_reviews = [r for r in reviews if r.has_modification]

        if not modification_reviews:
            logger.warning("No reviews with modifications found")
            return []

        # Deduplicate identical review text while preserving order
        seen_texts = set()
        unique_reviews = []
        for r in modification_reviews:
            key = r.text.strip()
            if key not in seen_texts:
                seen_texts.add(key)
                unique_reviews.append(r)

        logger.info(
            f"Extracting modifications from {len(unique_reviews)} unique reviews"
        )

        results: list[tuple[ModificationObject, Review]] = []
        for i, review in enumerate(unique_reviews):
            logger.info(
                f"Processing review {i + 1}/{len(unique_reviews)}: "
                f"{review.text[:80]}..."
            )
            modifications = self.extract_modifications(review, recipe)
            for modification in modifications:
                results.append((modification, review))
            if not modifications:
                logger.info(
                    f"Review {i + 1} yielded no concrete tested modifications"
                )

        logger.info(
            f"Extracted {len(results)} atomic modifications from "
            f"{len(unique_reviews)} reviews"
        )
        return results
