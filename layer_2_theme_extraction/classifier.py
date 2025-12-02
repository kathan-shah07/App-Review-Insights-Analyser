"""
LLM-based review classifier that assigns each review to one of 5 themes
"""
import json
import re
import time
from typing import List, Dict, Any, Optional
from collections import Counter

from utils.llm_client import LLMClient
from layer_2_theme_extraction.theme_config import (
    THEMES,
    get_theme_list,
    get_all_theme_descriptions,
    is_valid_theme,
    get_fallback_theme,
    MIN_REVIEW_LENGTH
)
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# Batch size for reviews per prompt
REVIEWS_PER_BATCH = 30


class ReviewClassifier:
    """Classify reviews into predefined themes using LLM"""
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        """
        Initialize classifier
        
        Args:
            llm_client: LLM client instance (creates new one if not provided)
        """
        self.llm_client = llm_client or LLMClient()
        self.themes = get_theme_list()
        self.theme_descriptions = get_all_theme_descriptions()
        self.fallback_theme = get_fallback_theme()
    
    def classify_batch(self, reviews: List[Dict[str, Any]], batch_name: str = "batch") -> List[Dict[str, Any]]:
        """
        Classify a batch of reviews into themes
        Reviews are grouped into batches of 30 and processed with retry logic and delays
        
        Args:
            reviews: List of review dictionaries with review_id, title, text
            batch_name: Name for logging purposes
            
        Returns:
            List of classification results with review_id, chosen_theme, short_reason
        """
        if not reviews:
            logger.info(f"No reviews to classify for {batch_name}")
            return []
        
        # Filter out short reviews
        valid_reviews = [
            review for review in reviews
            if len(review.get('text', '').strip()) >= MIN_REVIEW_LENGTH
        ]
        
        if not valid_reviews:
            logger.info(f"No valid reviews (>= {MIN_REVIEW_LENGTH} chars) to classify for {batch_name}")
            return []
        
        logger.info(f"Classifying {len(valid_reviews)} reviews for {batch_name} (batches of {REVIEWS_PER_BATCH})")
        
        # Split reviews into batches of 30
        batches = [
            valid_reviews[i:i + REVIEWS_PER_BATCH]
            for i in range(0, len(valid_reviews), REVIEWS_PER_BATCH)
        ]
        
        logger.info(f"Split into {len(batches)} batches")
        
        all_classifications = []
        total_processed = 0
        
        # Process each batch with retry logic and delays
        for batch_idx, batch_reviews in enumerate(batches, 1):
            batch_label = f"{batch_name}_batch_{batch_idx}"
            batch_size = len(batch_reviews)
            total_processed += batch_size
            
            logger.info(f"\n{'-' * 60}")
            logger.info(f"Processing {batch_label}: {batch_size} reviews")
            logger.info(f"Progress: {total_processed}/{len(valid_reviews)} reviews ({total_processed/len(valid_reviews)*100:.1f}%)")
            
            # Log review IDs in this batch
            review_ids = [r.get('review_id', 'unknown')[:50] for r in batch_reviews[:5]]  # Show first 5
            if len(batch_reviews) > 5:
                logger.info(f"Review IDs in batch: {', '.join(review_ids)} ... (+{len(batch_reviews)-5} more)")
            else:
                logger.info(f"Review IDs in batch: {', '.join(review_ids)}")
            
            # Classify this batch with retry logic
            batch_classifications = self._classify_batch_with_retry(
                batch_reviews,
                batch_label
            )
            
            # Log classification results for this batch
            if batch_classifications:
                batch_theme_counts = {}
                for cls in batch_classifications:
                    theme = cls.get('chosen_theme', 'Unknown')
                    batch_theme_counts[theme] = batch_theme_counts.get(theme, 0) + 1
                
                logger.info(f"Batch {batch_idx} classified: {len(batch_classifications)} reviews")
                if batch_theme_counts:
                    theme_summary = ', '.join([f"{theme} ({count})" for theme, count in sorted(batch_theme_counts.items(), key=lambda x: x[1], reverse=True)[:3]])
                    logger.info(f"  Themes: {theme_summary}")
            
            all_classifications.extend(batch_classifications)
            
            # Add delay between batches (except for the last one)
            if batch_idx < len(batches):
                delay = settings.LLM_BATCH_DELAY
                logger.info(f"Waiting {delay}s before next batch...")
                time.sleep(delay)
        
        logger.info(f"Successfully classified {len(all_classifications)} reviews for {batch_name}")
        return all_classifications
    
    def _classify_batch_with_retry(self, reviews: List[Dict[str, Any]], batch_label: str) -> List[Dict[str, Any]]:
        """
        Classify a batch of reviews with retry logic and exponential backoff
        
        Args:
            reviews: List of reviews to classify
            batch_label: Label for logging
            
        Returns:
            List of classification results
        """
        max_retries = settings.LLM_RETRY_ATTEMPTS
        base_delay = settings.LLM_RETRY_DELAY_BASE
        rate_limit_delay = settings.LLM_RATE_LIMIT_DELAY
        
        for attempt in range(1, max_retries + 1):
            try:
                # Build classification prompt
                prompt = self._build_classification_prompt(reviews)
                
                # Get LLM response
                raw_response = self.llm_client.generate(prompt)
                classifications = self._parse_llm_response(raw_response, reviews)
                
                # Validate and apply guardrails
                validated_classifications = self._validate_classifications(classifications, reviews)
                
                logger.info(f"Successfully classified {len(validated_classifications)} reviews for {batch_label}")
                return validated_classifications
                
            except Exception as e:
                error_str = str(e)
                is_rate_limit = (
                    "429" in error_str or 
                    "quota" in error_str.lower() or
                    "rate limit" in error_str.lower() or
                    "ResourceExhausted" in error_str
                )
                is_deadline = "504" in error_str or "DeadlineExceeded" in error_str
                
                if attempt < max_retries:
                    # Calculate delay
                    if is_rate_limit:
                        delay = rate_limit_delay
                        logger.warning(
                            f"Rate limit hit for {batch_label} (attempt {attempt}/{max_retries}). "
                            f"Waiting {delay}s before retry..."
                        )
                    elif is_deadline:
                        # Exponential backoff for deadline errors
                        delay = base_delay * (2 ** (attempt - 1))
                        logger.warning(
                            f"Deadline exceeded for {batch_label} (attempt {attempt}/{max_retries}). "
                            f"Waiting {delay}s before retry..."
                        )
                    else:
                        # Exponential backoff for other errors
                        delay = base_delay * (2 ** (attempt - 1))
                        logger.warning(
                            f"Error classifying {batch_label} (attempt {attempt}/{max_retries}): {error_str}. "
                            f"Waiting {delay}s before retry..."
                        )
                    
                    time.sleep(delay)
                else:
                    # Max retries reached, use fallback
                    logger.error(
                        f"Max retries reached for {batch_label}. Using fallback classifications. "
                        f"Error: {error_str}"
                    )
                    return self._create_fallback_classifications(reviews)
        
        # Should not reach here, but just in case
        return self._create_fallback_classifications(reviews)
    
    def _build_classification_prompt(self, reviews: List[Dict[str, Any]]) -> str:
        """
        Build the LLM classification prompt
        
        Args:
            reviews: List of reviews to classify
            
        Returns:
            Classification prompt string
        """
        # Build theme list
        theme_block = "\n".join(
            f"- {theme}: {desc}" 
            for theme, desc in self.theme_descriptions.items()
        )
        
        # Build review list (exclude internal fields like _week_key)
        reviews_block = ""
        for review in reviews:
            review_id = review.get('review_id', 'unknown')
            title = review.get('title', '')
            text = review.get('text', '')
            if title:
                reviews_block += f"\nReview ID: {review_id}\nTitle: {title}\nText: {text}\n"
            else:
                reviews_block += f"\nReview ID: {review_id}\nText: {text}\n"
        
        prompt = f"""You are tagging stock broking app reviews into at most 5 fixed themes.

Allowed themes:

{theme_block}

For each review, output:
- review_id
- chosen_theme (must be exactly one from the above list)
- short_reason (1 sentence, no PII)

Reviews:

{reviews_block}

Output format: Return a JSON array where each object has:
{{
  "review_id": "<review_id>",
  "chosen_theme": "<exact theme name from allowed list>",
  "short_reason": "<one sentence reason, no PII>"
}}

Return ONLY valid JSON, no markdown or additional text."""
        
        return prompt
    
    def _parse_llm_response(self, raw_response: str, reviews: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Parse LLM response into classification results
        
        Args:
            raw_response: Raw LLM response text
            reviews: Original reviews list (for fallback)
            
        Returns:
            List of classification dictionaries
        """
        # Clean response
        cleaned = raw_response.strip()
        
        # Remove markdown code blocks if present
        if "```" in cleaned:
            # Extract JSON from code blocks
            json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', cleaned, re.DOTALL)
            if json_match:
                cleaned = json_match.group(1)
            else:
                # Try to find JSON array in the text
                json_match = re.search(r'(\[.*?\])', cleaned, re.DOTALL)
                if json_match:
                    cleaned = json_match.group(1)
        
        # Try to parse as JSON
        try:
            data = json.loads(cleaned)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                # Single classification wrapped in dict
                return [data]
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON response, attempting line-based parsing")
            # Try line-based parsing as fallback
            return self._parse_line_based_response(raw_response, reviews)
        
        return []
    
    def _parse_line_based_response(self, text: str, reviews: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Parse line-based response format as fallback
        
        Args:
            text: Response text
            reviews: Original reviews list
            
        Returns:
            List of classification dictionaries
        """
        classifications = []
        lines = text.split('\n')
        
        current_review_id = None
        current_theme = None
        current_reason = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Try to extract review_id
            if 'review_id' in line.lower() or 'id:' in line.lower():
                match = re.search(r'(?:review_id|id)[:\s]+([^\s,]+)', line, re.IGNORECASE)
                if match:
                    current_review_id = match.group(1)
            
            # Try to extract theme
            if 'chosen_theme' in line.lower() or 'theme:' in line.lower():
                for theme in self.themes:
                    if theme.lower() in line.lower():
                        current_theme = theme
                        break
            
            # Try to extract reason
            if 'short_reason' in line.lower() or 'reason:' in line.lower():
                reason_match = re.search(r'(?:short_reason|reason)[:\s]+(.+)', line, re.IGNORECASE)
                if reason_match:
                    current_reason = reason_match.group(1).strip()
            
            # If we have all fields, add classification
            if current_review_id and current_theme and current_reason:
                classifications.append({
                    "review_id": current_review_id,
                    "chosen_theme": current_theme,
                    "short_reason": current_reason
                })
                # Reset for next review
                current_review_id = None
                current_theme = None
                current_reason = None
        
        return classifications
    
    def _validate_classifications(self, classifications: List[Dict[str, Any]], reviews: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validate classifications and apply guardrails
        
        Args:
            classifications: Raw classification results
            reviews: Original reviews list
            
        Returns:
            Validated classification results
        """
        validated = []
        review_ids = {review.get('review_id') for review in reviews}
        classification_map = {c.get('review_id'): c for c in classifications}
        
        for review in reviews:
            review_id = review.get('review_id')
            classification = classification_map.get(review_id)
            
            if classification:
                theme = classification.get('chosen_theme', '').strip()
                reason = classification.get('short_reason', 'No reason provided')
                
                # Validate theme
                if not is_valid_theme(theme):
                    logger.warning(f"Invalid theme '{theme}' for review {review_id}, using fallback")
                    theme = self.fallback_theme
                    reason = f"Fallback applied: invalid theme '{classification.get('chosen_theme')}'"
                
                validated.append({
                    "review_id": review_id,
                    "chosen_theme": theme,
                    "short_reason": reason
                })
            else:
                # Missing classification - use fallback
                logger.warning(f"No classification found for review {review_id}, using fallback")
                validated.append({
                    "review_id": review_id,
                    "chosen_theme": self.fallback_theme,
                    "short_reason": "Fallback: LLM did not classify this review"
                })
        
        return validated
    
    def _create_fallback_classifications(self, reviews: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Create fallback classifications when LLM fails
        
        Args:
            reviews: List of reviews
            
        Returns:
            List of fallback classifications
        """
        return [
            {
                "review_id": review.get('review_id', 'unknown'),
                "chosen_theme": self.fallback_theme,
                "short_reason": "Fallback classification due to LLM error"
            }
            for review in reviews
        ]


def aggregate_theme_counts(classifications: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Aggregate theme counts from classifications
    
    Args:
        classifications: List of classification results
        
    Returns:
        Dictionary mapping theme names to counts
    """
    theme_counts = Counter()
    for classification in classifications:
        theme = classification.get('chosen_theme', '')
        if theme:
            theme_counts[theme] += 1
    return dict(theme_counts)


def get_top_themes_by_count(classifications: List[Dict[str, Any]], max_themes: int = 5) -> List[tuple[str, int]]:
    """
    Get top themes by count, sorted descending
    
    Args:
        classifications: List of classification results
        max_themes: Maximum number of themes to return
        
    Returns:
        List of (theme_name, count) tuples, sorted by count descending
    """
    theme_counts = aggregate_theme_counts(classifications)
    sorted_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)
    return sorted_themes[:max_themes]

