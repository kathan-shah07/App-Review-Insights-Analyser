"""
Final PII check and removal before sending
Uses regex patterns to detect and remove PII
"""
import re
from typing import List, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)


class PIIChecker:
    """Check and remove PII from email content"""
    
    # PII patterns to detect
    PII_PATTERNS = [
        # Email addresses
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', 'email'),
        # Phone numbers (various formats) - but not dates
        (r'\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}', 'phone'),
        # Indian phone numbers
        (r'\+?91[-.\s]?\d{10}', 'phone_india'),
        (r'\+?91[-.\s]?\d{4}[-.\s]?\d{3}[-.\s]?\d{3}', 'phone_india'),
        # UPI IDs (but not email addresses)
        (r'\b[\w.-]+@[\w.-]+\b', 'upi'),
        # Account IDs / Demat numbers (must contain digits and be uppercase or mixed case with numbers)
        (r'\b[A-Z0-9]{8,}\b', 'account_id'),
        # Credit card numbers (16 digits)
        (r'\b\d{4}[-.\s]?\d{4}[-.\s]?\d{4}[-.\s]?\d{4}\b', 'card'),
        # Social security numbers (if any)
        (r'\b\d{3}-\d{2}-\d{4}\b', 'ssn'),
    ]
    
    def __init__(self):
        """Initialize PII checker"""
        self.compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), pii_type)
            for pattern, pii_type in self.PII_PATTERNS
        ]
    
    def check_and_remove_pii(self, text: str, mask: bool = True) -> Tuple[str, List[str]]:
        """
        Check for PII and remove/mask it
        
        Args:
            text: Text to check
            mask: If True, mask PII with ***, otherwise remove it
            
        Returns:
            Tuple of (cleaned_text, detected_pii_list)
        """
        detected_pii = []
        cleaned_text = text
        
        for pattern, pii_type in self.compiled_patterns:
            matches = pattern.findall(cleaned_text)
            if matches:
                for match in matches:
                    # Skip if it's a common word or false positive
                    if self._is_false_positive(match, pii_type):
                        continue
                    
                    detected_pii.append(f"{pii_type}: {match}")
                    
                    if mask:
                        # Mask with ***
                        cleaned_text = cleaned_text.replace(match, '***')
                    else:
                        # Remove
                        cleaned_text = cleaned_text.replace(match, '')
        
        if detected_pii:
            logger.warning(f"Detected {len(detected_pii)} PII instances: {detected_pii[:5]}...")
        
        return cleaned_text, detected_pii
    
    def _is_false_positive(self, match: str, pii_type: str) -> bool:
        """
        Check if a match is a false positive
        
        Args:
            match: Matched string
            pii_type: Type of PII
            
        Returns:
            True if false positive, False otherwise
        """
        # Common false positives
        false_positives = [
            'http://', 'https://', 'www.', '.com', '.org', '.net',
            'example.com', 'test.com', 'localhost'
        ]
        
        match_lower = match.lower()
        for fp in false_positives:
            if fp in match_lower:
                return True
        
        # Skip very short matches for account_id
        if pii_type == 'account_id' and len(match) < 8:
            return True
        
        # Date patterns (YYYY-MM-DD, YYYY/MM/DD, etc.)
        date_pattern = re.compile(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}$')
        if date_pattern.match(match):
            return True
        
        # Year-only matches (like "2025")
        if pii_type == 'phone' and len(match) == 4 and match.isdigit():
            # Likely a year, not a phone number
            if match.startswith('19') or match.startswith('20'):
                return True
        
        # Skip common words that match account_id pattern
        common_words = ['covering', 'insights', 'feedback', 'product', 'pulse', 'weekly',
                       'december', 'november', 'october', 'january', 'february', 'march',
                       'april', 'may', 'june', 'july', 'august', 'september',
                       'provides', 'snapshot', 'overview', 'highlights', 'summary']
        if pii_type == 'account_id' and match_lower in common_words:
            return True
        
        # Account IDs should contain at least one digit or be all uppercase with numbers
        if pii_type == 'account_id':
            # If it's all letters (no digits), likely a word
            if not any(c.isdigit() for c in match):
                return True
            # If it's mixed case with no digits, likely a word
            if match != match.upper() and not any(c.isdigit() for c in match):
                return True
        
        return False
    
    def scrub_email(self, email_body: str) -> str:
        """
        Scrub email body for PII
        
        Args:
            email_body: Email body text
            
        Returns:
            Scrubbed email body
        """
        cleaned, detected = self.check_and_remove_pii(email_body, mask=True)
        
        if detected:
            logger.warning(f"Removed {len(detected)} PII instances from email")
            # If significant PII found, try LLM-based removal
            if len(detected) > 3:
                logger.warning("Significant PII detected, consider manual review")
        
        return cleaned
    
    def check_subject_line(self, subject: str) -> Tuple[str, bool]:
        """
        Check subject line for PII
        
        Args:
            subject: Subject line text
            
        Returns:
            Tuple of (cleaned_subject, has_pii)
        """
        cleaned, detected = self.check_and_remove_pii(subject, mask=True)
        has_pii = len(detected) > 0
        
        if has_pii:
            logger.warning(f"PII detected in subject line: {detected}")
        
        return cleaned, has_pii
