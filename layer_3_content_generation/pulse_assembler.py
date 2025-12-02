"""
Assemble weekly pulse document (≤250 words) with 3 themes, 3 quotes, 3 actions
Uses reduce stage to synthesize theme summaries into final weekly note
"""
import json
import re
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

from utils.llm_client import LLMClient
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_WORD_COUNT = 250


class PulseAssembler:
    """Assemble weekly pulse from theme summaries"""
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        """
        Initialize pulse assembler
        
        Args:
            llm_client: LLM client instance (creates new one if not provided)
        """
        self.llm_client = llm_client or LLMClient()
    
    def assemble_pulse(self, week_key: str, week_start: str, week_end: str,
                      theme_summaries: List[Dict[str, Any]], 
                      top_3_themes: List[tuple[str, int]],
                      max_retries: int = 3) -> Dict[str, Any]:
        """
        Assemble weekly pulse from theme summaries (reduce stage)
        
        Args:
            week_key: Week key (YYYY-MM-DD)
            week_start: Week start date
            week_end: Week end date
            theme_summaries: List of theme summary dictionaries
            top_3_themes: List of (theme_name, count) tuples for top 3 themes
            max_retries: Maximum retry attempts
            
        Returns:
            Dictionary with title, overview, themes, quotes, actions
        """
        logger.info(f"Assembling weekly pulse for week {week_key}")
        
        # Filter to top 3 themes only
        top_3_theme_names = [theme for theme, _ in top_3_themes[:3]]
        filtered_summaries = [
            summary for summary in theme_summaries
            if summary.get('theme') in top_3_theme_names
        ]
        
        logger.info(f"Using top 3 themes: {', '.join(top_3_theme_names)}")
        
        # Build synthesis prompt
        prompt = self._build_synthesis_prompt(week_start, week_end, filtered_summaries)
        
        # Generate pulse with retry logic
        for attempt in range(1, max_retries + 1):
            try:
                raw_response = self.llm_client.generate(prompt)
                pulse = self._parse_pulse_response(raw_response)
                
                if pulse:
                    # Enforce word limit
                    pulse = self._enforce_word_limit(pulse, max_retries)
                    return pulse
                else:
                    logger.warning(f"Failed to parse pulse response (attempt {attempt}/{max_retries})")
                    
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
                        logger.warning(f"Error assembling pulse (attempt {attempt}/{max_retries}): {error_str}. Waiting {delay}s...")
                    
                    time.sleep(delay)
                else:
                    logger.error(f"Max retries reached for pulse assembly. Error: {error_str}")
                    # Return fallback pulse
                    return self._create_fallback_pulse(week_key, top_3_theme_names)
        
        return self._create_fallback_pulse(week_key, top_3_theme_names)
    
    def _build_synthesis_prompt(self, week_start: str, week_end: str,
                                theme_summaries: List[Dict[str, Any]]) -> str:
        """
        Build the synthesis prompt for creating the weekly pulse
        
        Args:
            week_start: Week start date
            week_end: Week end date
            theme_summaries: List of theme summary dictionaries
            
        Returns:
            Prompt string
        """
        # Format theme summaries as JSON
        summaries_json = json.dumps(theme_summaries, indent=2)
        
        prompt = f"""You are creating a weekly product pulse for internal stakeholders
(Product, Growth, Support, Leadership)

Input:

Time window: {week_start} to {week_end}

Candidate themes with key points & quotes:

{summaries_json}

Constraints:

1. Select Top 3 themes by frequency + impact
2. Produce:
   - A short, crisp title for this week's pulse
   - A one-paragraph overview (max 60 words)
   - A bullet list of the Top 3 themes, each with a 1-sentence sentiment + key insight
   - 3 anonymized user quotes, 1–2 lines, each tagged with theme
   - 3 specific action ideas, each tied to a theme (e.g., "Improve UPI fallback", "Optimize chart load time", "Fix SIP order retry logic")

Style & Limits:

- Total length ≤ 250 words
- Use crisp bullets; executive-friendly
- Neutral, fact-based tone
- No PII: remove all names, emails, phone numbers, account IDs, demat numbers, UPI IDs

Output JSON:

{{
  "title": "...",
  "overview": "...",
  "themes": [
    {{"name": "...", "summary": "..."}},
    {{"name": "...", "summary": "..."}},
    {{"name": "...", "summary": "..."}}
  ],
  "quotes": ["...", "...", "..."],
  "actions": ["...", "...", "..."]
}}

Return ONLY valid JSON, no markdown or additional text."""
        
        return prompt
    
    def _parse_pulse_response(self, raw_response: str) -> Optional[Dict[str, Any]]:
        """
        Parse LLM response into pulse structure
        
        Args:
            raw_response: Raw LLM response
            
        Returns:
            Parsed pulse dictionary or None if parsing failed
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
            
            # Ensure required fields
            pulse = {
                "title": data.get('title', 'Weekly Product Pulse'),
                "overview": data.get('overview', ''),
                "themes": data.get('themes', []),
                "quotes": data.get('quotes', []),
                "actions": data.get('actions', [])
            }
            
            # Validate types
            if not isinstance(pulse['themes'], list):
                pulse['themes'] = []
            if not isinstance(pulse['quotes'], list):
                pulse['quotes'] = []
            if not isinstance(pulse['actions'], list):
                pulse['actions'] = []
            
            # Ensure exactly 3 themes, quotes, and actions
            pulse['themes'] = pulse['themes'][:3]
            pulse['quotes'] = pulse['quotes'][:3]
            pulse['actions'] = pulse['actions'][:3]
            
            return pulse
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse pulse JSON response: {e}")
            return None
    
    def _enforce_word_limit(self, pulse: Dict[str, Any], max_retries: int = 3) -> Dict[str, Any]:
        """
        Enforce 250-word limit on pulse
        
        Args:
            pulse: Pulse dictionary
            max_retries: Maximum retry attempts for compression
            
        Returns:
            Pulse dictionary within word limit
        """
        word_count = self._count_words(pulse)
        
        if word_count <= MAX_WORD_COUNT:
            logger.info(f"Pulse word count: {word_count} (within limit of {MAX_WORD_COUNT})")
            return pulse
        
        logger.warning(f"Pulse word count: {word_count} (exceeds limit of {MAX_WORD_COUNT}), compressing...")
        
        # Compress the pulse
        for attempt in range(1, max_retries + 1):
            try:
                compressed = self._compress_pulse(pulse)
                compressed_word_count = self._count_words(compressed)
                
                if compressed_word_count <= MAX_WORD_COUNT:
                    logger.info(f"Compressed pulse to {compressed_word_count} words")
                    return compressed
                else:
                    logger.warning(f"Compression attempt {attempt}: Still {compressed_word_count} words, retrying...")
                    pulse = compressed  # Use compressed version for next attempt
                    
            except Exception as e:
                logger.warning(f"Compression attempt {attempt} failed: {e}")
                if attempt < max_retries:
                    time.sleep(settings.LLM_RETRY_DELAY_BASE)
        
        # If compression failed, truncate manually
        logger.warning("Compression failed, applying manual truncation")
        return self._manual_truncate(pulse)
    
    def _compress_pulse(self, pulse: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compress pulse using LLM
        
        Args:
            pulse: Pulse dictionary to compress
            
        Returns:
            Compressed pulse dictionary
        """
        pulse_text = self._pulse_to_text(pulse)
        
        prompt = f"""Compress this note to ≤{MAX_WORD_COUNT} words while preserving:

- 3 themes
- 3 quotes
- 3 action ideas
- Bullet-based format
- No PII

Current note:

{pulse_text}

Return the same JSON structure with compressed content. Keep all fields but make them more concise.

Return ONLY valid JSON, no markdown or additional text."""
        
        raw_response = self.llm_client.generate(prompt)
        compressed = self._parse_pulse_response(raw_response)
        
        return compressed or pulse
    
    def _pulse_to_text(self, pulse: Dict[str, Any]) -> str:
        """Convert pulse dictionary to text for compression"""
        text_parts = []
        
        if pulse.get('title'):
            text_parts.append(f"Title: {pulse['title']}")
        
        if pulse.get('overview'):
            text_parts.append(f"Overview: {pulse['overview']}")
        
        if pulse.get('themes'):
            text_parts.append("Themes:")
            for theme in pulse['themes']:
                name = theme.get('name', '')
                summary = theme.get('summary', '')
                text_parts.append(f"  - {name}: {summary}")
        
        if pulse.get('quotes'):
            text_parts.append("Quotes:")
            for quote in pulse['quotes']:
                text_parts.append(f"  - {quote}")
        
        if pulse.get('actions'):
            text_parts.append("Actions:")
            for action in pulse['actions']:
                text_parts.append(f"  - {action}")
        
        return "\n".join(text_parts)
    
    def _count_words(self, pulse: Dict[str, Any]) -> int:
        """
        Count total words in pulse
        
        Args:
            pulse: Pulse dictionary
            
        Returns:
            Total word count
        """
        text_parts = []
        
        if pulse.get('title'):
            text_parts.append(pulse['title'])
        
        if pulse.get('overview'):
            text_parts.append(pulse['overview'])
        
        if pulse.get('themes'):
            for theme in pulse['themes']:
                text_parts.append(theme.get('name', ''))
                text_parts.append(theme.get('summary', ''))
        
        if pulse.get('quotes'):
            text_parts.extend(pulse['quotes'])
        
        if pulse.get('actions'):
            text_parts.extend(pulse['actions'])
        
        full_text = " ".join(text_parts)
        word_count = len(full_text.split())
        
        return word_count
    
    def _manual_truncate(self, pulse: Dict[str, Any]) -> Dict[str, Any]:
        """
        Manually truncate pulse if compression fails
        
        Args:
            pulse: Pulse dictionary
            
        Returns:
            Truncated pulse dictionary
        """
        truncated = pulse.copy()
        
        # Truncate overview
        if truncated.get('overview'):
            words = truncated['overview'].split()
            if len(words) > 60:
                truncated['overview'] = ' '.join(words[:60]) + '...'
        
        # Truncate theme summaries
        if truncated.get('themes'):
            for theme in truncated['themes']:
                if theme.get('summary'):
                    words = theme['summary'].split()
                    if len(words) > 20:
                        theme['summary'] = ' '.join(words[:20]) + '...'
        
        # Truncate quotes
        if truncated.get('quotes'):
            truncated['quotes'] = [
                quote[:100] + '...' if len(quote) > 100 else quote
                for quote in truncated['quotes'][:3]
            ]
        
        # Truncate actions
        if truncated.get('actions'):
            truncated['actions'] = [
                action[:80] + '...' if len(action) > 80 else action
                for action in truncated['actions'][:3]
            ]
        
        return truncated
    
    def _create_fallback_pulse(self, week_key: str, theme_names: List[str]) -> Dict[str, Any]:
        """
        Create fallback pulse if LLM fails
        
        Args:
            week_key: Week key
            theme_names: List of theme names
            
        Returns:
            Fallback pulse dictionary
        """
        return {
            "title": f"Weekly Product Pulse - {week_key}",
            "overview": f"Summary of user feedback for week {week_key}. Top themes identified: {', '.join(theme_names[:3])}.",
            "themes": [
                {"name": theme, "summary": f"User feedback related to {theme}."}
                for theme in theme_names[:3]
            ],
            "quotes": [
                "User feedback collected for this theme.",
                "Additional insights from user reviews.",
                "Further user sentiment analysis."
            ],
            "actions": [
                "Review and prioritize improvements based on user feedback.",
                "Engage with product team to address key concerns.",
                "Monitor trends and track improvement metrics."
            ]
        }
