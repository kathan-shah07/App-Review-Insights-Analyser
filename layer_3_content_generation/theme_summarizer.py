"""
Theme summarization using LLM map-reduce approach
Chunks reviews per theme and extracts key points and candidate quotes
"""
import json
import re
import time
from typing import List, Dict, Any, Optional
from collections import defaultdict

from utils.llm_client import LLMClient
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# Reviews per chunk for summarization
REVIEWS_PER_CHUNK = 30


class ThemeSummarizer:
    """Summarize reviews per theme using chunked map-reduce approach"""
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        """
        Initialize theme summarizer
        
        Args:
            llm_client: LLM client instance (creates new one if not provided)
        """
        self.llm_client = llm_client or LLMClient()
    
    def summarize_theme(self, theme_name: str, reviews: List[Dict[str, Any]], 
                        max_retries: int = 3) -> Dict[str, Any]:
        """
        Summarize reviews for a specific theme
        
        Args:
            theme_name: Name of the theme
            reviews: List of reviews with text and theme assignment
            max_retries: Maximum retry attempts
            
        Returns:
            Dictionary with theme, key_points, and candidate_quotes
        """
        if not reviews:
            logger.warning(f"No reviews provided for theme: {theme_name}")
            return {
                "theme": theme_name,
                "key_points": [],
                "candidate_quotes": []
            }
        
        logger.info(f"Summarizing theme '{theme_name}' with {len(reviews)} reviews")
        
        # Extract review texts (already cleaned and PII-redacted from layer-1)
        review_texts = [r.get('text', '').strip() for r in reviews if r.get('text', '').strip()]
        
        if not review_texts:
            logger.warning(f"No valid review texts for theme: {theme_name}")
            return {
                "theme": theme_name,
                "key_points": [],
                "candidate_quotes": []
            }
        
        # Chunk reviews if needed
        chunks = [
            review_texts[i:i + REVIEWS_PER_CHUNK]
            for i in range(0, len(review_texts), REVIEWS_PER_CHUNK)
        ]
        
        logger.info(f"Split into {len(chunks)} chunks for theme '{theme_name}'")
        
        all_key_points = []
        all_candidate_quotes = []
        
        # Process each chunk
        for chunk_idx, chunk_reviews in enumerate(chunks, 1):
            logger.info(f"Processing chunk {chunk_idx}/{len(chunks)} for theme '{theme_name}' ({len(chunk_reviews)} reviews)")
            
            chunk_result = self._summarize_chunk(theme_name, chunk_reviews, max_retries)
            
            if chunk_result:
                all_key_points.extend(chunk_result.get('key_points', []))
                all_candidate_quotes.extend(chunk_result.get('candidate_quotes', []))
            
            # Add delay between chunks
            if chunk_idx < len(chunks):
                time.sleep(settings.LLM_BATCH_DELAY)
        
        # Deduplicate and limit
        unique_key_points = list(dict.fromkeys(all_key_points))[:10]  # Keep top 10 unique points
        unique_quotes = list(dict.fromkeys(all_candidate_quotes))[:5]  # Keep top 5 unique quotes
        
        logger.info(f"Theme '{theme_name}': Extracted {len(unique_key_points)} key points, {len(unique_quotes)} candidate quotes")
        
        return {
            "theme": theme_name,
            "key_points": unique_key_points,
            "candidate_quotes": unique_quotes
        }
    
    def _summarize_chunk(self, theme_name: str, review_texts: List[str], 
                        max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """
        Summarize a chunk of reviews for a theme
        
        Args:
            theme_name: Name of the theme
            review_texts: List of review text strings
            max_retries: Maximum retry attempts
            
        Returns:
            Dictionary with key_points and candidate_quotes, or None if failed
        """
        prompt = self._build_summarization_prompt(theme_name, review_texts)
        
        for attempt in range(1, max_retries + 1):
            try:
                raw_response = self.llm_client.generate(prompt)
                result = self._parse_summarization_response(raw_response, theme_name)
                
                if result:
                    return result
                else:
                    logger.warning(f"Failed to parse summarization response (attempt {attempt}/{max_retries})")
                    
            except Exception as e:
                error_str = str(e)
                is_rate_limit = (
                    "429" in error_str or 
                    "quota" in error_str.lower() or
                    "rate limit" in error_str.lower() or
                    "ResourceExhausted" in error_str
                )
                
                if attempt < max_retries:
                    if is_rate_limit:
                        delay = settings.LLM_RATE_LIMIT_DELAY
                        logger.warning(f"Rate limit hit (attempt {attempt}/{max_retries}). Waiting {delay}s...")
                    else:
                        delay = settings.LLM_RETRY_DELAY_BASE * (2 ** (attempt - 1))
                        logger.warning(f"Error summarizing chunk (attempt {attempt}/{max_retries}): {error_str}. Waiting {delay}s...")
                    
                    time.sleep(delay)
                else:
                    logger.error(f"Max retries reached for theme '{theme_name}' chunk. Error: {error_str}")
                    return None
        
        return None
    
    def _build_summarization_prompt(self, theme_name: str, review_texts: List[str]) -> str:
        """
        Build the summarization prompt for a chunk
        
        Args:
            theme_name: Name of the theme
            review_texts: List of review text strings
            
        Returns:
            Prompt string
        """
        reviews_block = "\n".join([
            f"{idx + 1}. {text}"
            for idx, text in enumerate(review_texts)
        ])
        
        prompt = f"""You are summarizing user feedback for a stock broking app.

Theme: {theme_name}

Reviews (cleaned, no PII):

{reviews_block}

Tasks:

1. Extract 3–5 factual, neutral key points about this theme
2. Identify up to 3 short, vivid quotes capturing sentiment
3. Do NOT include names, usernames, emails, IDs, demat numbers, or masked numbers
4. If a quote contains PII, rewrite it to keep meaning but fully remove personal details

Return JSON:

{{
  "theme": "{theme_name}",
  "key_points": ["...", "..."],
  "candidate_quotes": ["...", "...", "..."]
}}

Keep everything concise and non-promotional. Quotes should be 1-2 lines maximum.

Return ONLY valid JSON, no markdown or additional text."""
        
        return prompt
    
    def _parse_summarization_response(self, raw_response: str, theme_name: str) -> Optional[Dict[str, Any]]:
        """
        Parse LLM response into summarization result
        
        Args:
            raw_response: Raw LLM response
            theme_name: Theme name for validation
            
        Returns:
            Parsed result dictionary or None if parsing failed
        """
        # Clean response
        cleaned = raw_response.strip()
        
        # Remove markdown code blocks if present
        if "```" in cleaned:
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', cleaned, re.DOTALL)
            if json_match:
                cleaned = json_match.group(1)
            else:
                json_match = re.search(r'(\{.*?\})', cleaned, re.DOTALL)
                if json_match:
                    cleaned = json_match.group(1)
        
        try:
            data = json.loads(cleaned)
            
            # Validate structure
            if not isinstance(data, dict):
                return None
            
            # Ensure theme matches
            if data.get('theme') != theme_name:
                data['theme'] = theme_name
            
            # Ensure required fields
            result = {
                "theme": data.get('theme', theme_name),
                "key_points": data.get('key_points', []),
                "candidate_quotes": data.get('candidate_quotes', [])
            }
            
            # Validate types
            if not isinstance(result['key_points'], list):
                result['key_points'] = []
            if not isinstance(result['candidate_quotes'], list):
                result['candidate_quotes'] = []
            
            return result
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response for theme '{theme_name}': {e}")
            return None

