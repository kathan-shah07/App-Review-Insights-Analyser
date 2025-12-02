"""
Email content drafting via LLM
Generates email body from weekly pulse note
"""
import json
import os
import time
from typing import Dict, Any, Optional

from utils.llm_client import LLMClient
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_EMAIL_WORDS = 350


class EmailDrafter:
    """Draft email content from weekly pulse"""
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        """
        Initialize email drafter
        
        Args:
            llm_client: LLM client instance (creates new one if not provided)
        """
        self.llm_client = llm_client or LLMClient()
        self.product_name = os.getenv("PRODUCT_NAME", "Groww")
    
    def draft_email_body(self, pulse_data: Dict[str, Any], 
                         max_retries: int = 3) -> str:
        """
        Draft email body from weekly pulse
        
        Args:
            pulse_data: Weekly pulse data dictionary
            max_retries: Maximum retry attempts
            
        Returns:
            Email body string (plain text)
        """
        week_key = pulse_data.get('week_key', '')
        week_start = pulse_data.get('week_start_date', '')
        week_end = pulse_data.get('week_end_date', '')
        pulse = pulse_data.get('pulse', {})
        
        logger.info(f"Drafting email body for week {week_key}")
        
        prompt = self._build_email_prompt(pulse, week_start, week_end)
        
        for attempt in range(1, max_retries + 1):
            try:
                email_body = self.llm_client.generate(prompt)
                
                # Clean and validate
                email_body = self._clean_email_body(email_body)
                
                # Check word count
                word_count = len(email_body.split())
                if word_count > MAX_EMAIL_WORDS:
                    logger.warning(f"Email body exceeds {MAX_EMAIL_WORDS} words ({word_count}), compressing...")
                    email_body = self._compress_email(email_body, max_retries)
                
                logger.info(f"Email body drafted: {len(email_body.split())} words")
                return email_body
                
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
                        logger.warning(f"Error drafting email (attempt {attempt}/{max_retries}): {error_str}. Waiting {delay}s...")
                    
                    time.sleep(delay)
                else:
                    logger.error(f"Max retries reached for email drafting. Error: {error_str}")
                    return self._create_fallback_email_body(pulse, week_start, week_end)
        
        return self._create_fallback_email_body(pulse, week_start, week_end)
    
    def _build_email_prompt(self, pulse: Dict[str, Any], 
                            week_start: str, week_end: str) -> str:
        """
        Build the email drafting prompt
        
        Args:
            pulse: Pulse dictionary
            week_start: Week start date
            week_end: Week end date
            
        Returns:
            Prompt string
        """
        pulse_json = json.dumps(pulse, indent=2)
        
        prompt = f"""You are drafting an internal weekly email sharing the latest product pulse.

Audience:

- Product & Growth: want to see what to fix or double down on.
- Support: wants to know what to acknowledge and celebrate.
- Leadership: wants a quick pulse, key risks, and wins.

Input (weekly note JSON):

{pulse_json}

Tasks:

- Write an email body only (no subject line).
- Structure:

  1) 2–3 line intro explaining the time window and the product/program.

  2) Embed the weekly pulse note in a clean, scannable format:

     - Title

     - Overview

     - Bulleted Top 3 themes

     - Bulleted 3 quotes

     - Bulleted 3 action ideas

  3) End with a short closing line and invite replies.

Constraints:

- Professional, neutral tone with a hint of warmth.
- No names, emails, or IDs. If present in quotes, anonymize generically (e.g., "investor").
- Keep the whole email under {MAX_EMAIL_WORDS} words.
- Output plain text only (no HTML).

Time window: {week_start} to {week_end}
Product: {self.product_name}

Return ONLY the email body text, no markdown formatting or code blocks."""
        
        return prompt
    
    def _clean_email_body(self, email_body: str) -> str:
        """
        Clean email body (remove markdown, code blocks, etc.)
        
        Args:
            email_body: Raw email body
            
        Returns:
            Cleaned email body
        """
        cleaned = email_body.strip()
        
        # Remove markdown code blocks if present
        if "```" in cleaned:
            lines = cleaned.split('\n')
            # Remove lines with ```
            cleaned = '\n'.join([line for line in lines if not line.strip().startswith('```')])
        
        # Remove leading/trailing whitespace from each line
        lines = [line.rstrip() for line in cleaned.split('\n')]
        cleaned = '\n'.join(lines)
        
        return cleaned.strip()
    
    def _compress_email(self, email_body: str, max_retries: int = 3) -> str:
        """
        Compress email if it exceeds word limit
        
        Args:
            email_body: Email body to compress
            max_retries: Maximum retry attempts
            
        Returns:
            Compressed email body
        """
        prompt = f"""Compress this email to under {MAX_EMAIL_WORDS} words while preserving:

- 2-3 line intro
- All 3 themes
- All 3 quotes
- All 3 action ideas
- Closing line

Email to compress:

{email_body}

Return ONLY the compressed email body, no markdown or additional text."""
        
        for attempt in range(1, max_retries + 1):
            try:
                compressed = self.llm_client.generate(prompt)
                compressed = self._clean_email_body(compressed)
                
                word_count = len(compressed.split())
                if word_count <= MAX_EMAIL_WORDS:
                    return compressed
                else:
                    logger.warning(f"Compression attempt {attempt}: Still {word_count} words")
                    
            except Exception as e:
                logger.warning(f"Compression attempt {attempt} failed: {e}")
                if attempt < max_retries:
                    time.sleep(settings.LLM_RETRY_DELAY_BASE)
        
        # Manual truncation fallback
        return self._manual_truncate_email(email_body)
    
    def _manual_truncate_email(self, email_body: str) -> str:
        """
        Manually truncate email if compression fails
        
        Args:
            email_body: Email body to truncate
            
        Returns:
            Truncated email body
        """
        words = email_body.split()
        if len(words) <= MAX_EMAIL_WORDS:
            return email_body
        
        # Keep first MAX_EMAIL_WORDS words
        truncated_words = words[:MAX_EMAIL_WORDS]
        return ' '.join(truncated_words) + '...'
    
    def _create_fallback_email_body(self, pulse: Dict[str, Any],
                                    week_start: str, week_end: str) -> str:
        """
        Create fallback email body if LLM fails
        
        Args:
            pulse: Pulse dictionary
            week_start: Week start date
            week_end: Week end date
            
        Returns:
            Fallback email body
        """
        title = pulse.get('title', 'Weekly Product Pulse')
        overview = pulse.get('overview', '')
        themes = pulse.get('themes', [])
        quotes = pulse.get('quotes', [])
        actions = pulse.get('actions', [])
        
        email = f"""Hi Team,

Here's the weekly product pulse for {week_start} to {week_end} for {self.product_name}.

{title}

{overview}

Top Themes:
"""
        
        for theme in themes[:3]:
            name = theme.get('name', '')
            summary = theme.get('summary', '')
            email += f"\n• {name}: {summary}\n"
        
        email += "\nUser Quotes:\n"
        for quote in quotes[:3]:
            email += f"\n• \"{quote}\"\n"
        
        email += "\nAction Items:\n"
        for action in actions[:3]:
            email += f"\n• {action}\n"
        
        email += "\n\nFeel free to reply with questions or feedback.\n\nBest regards"
        
        return email
    
    def generate_subject_line(self, week_start: str, week_end: str) -> str:
        """
        Generate email subject line
        
        Args:
            week_start: Week start date
            week_end: Week end date
            
        Returns:
            Subject line string
        """
        return f"Weekly Product Pulse – {self.product_name} ({week_start}–{week_end})"

