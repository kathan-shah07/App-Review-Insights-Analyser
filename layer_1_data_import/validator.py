"""
Schema validator and PII detector for reviews
"""
import re
from typing import Dict, Optional
from datetime import datetime

# Language detection
try:
    from langdetect import detect_langs, LangDetectException
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False
    logger_temp = __import__('logging').getLogger(__name__)
    logger_temp.warning("langdetect not available. Language detection will be disabled.")

# Emoji detection
try:
    import emoji
    EMOJI_LIB_AVAILABLE = True
except ImportError:
    EMOJI_LIB_AVAILABLE = False
    logger_temp = __import__('logging').getLogger(__name__)
    logger_temp.warning("emoji library not available. Using regex-based emoji detection.")

from utils.logger import get_logger

logger = get_logger(__name__)


class PIIDetector:
    """Detect and redact PII from review text"""
    
    # Email pattern
    EMAIL_PATTERN = re.compile(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    )
    
    # Phone number patterns (various formats)
    PHONE_PATTERNS = [
        re.compile(r'\b\d{10}\b'),  # 10 digits
        re.compile(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b'),  # US format
        re.compile(r'\b\+?\d{1,3}[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}\b'),  # International
        re.compile(r'\b\d{5}[-.\s]?\d{5}\b'),  # Indian format
    ]
    
    # Account/Order ID patterns
    ACCOUNT_ID_PATTERN = re.compile(
        r'\b(?:account|order|transaction|ref|id)[\s:]*#?\s*(?:\w+\s+)*\d{6,}\b',
        re.IGNORECASE
    )
    
    # Username/handle patterns
    USERNAME_PATTERN = re.compile(r'@\w+')
    
    @classmethod
    def detect_and_redact(cls, text: str) -> str:
        """
        Detect and redact PII from text
        
        Args:
            text: Input text that may contain PII
        
        Returns:
            Text with PII redacted
        """
        if not text:
            return text
        
        redacted_text = text
        
        # Redact emails
        redacted_text = cls.EMAIL_PATTERN.sub('[REDACTED_EMAIL]', redacted_text)
        
        # Redact account/order IDs first (more specific patterns)
        redacted_text = cls.ACCOUNT_ID_PATTERN.sub('[REDACTED_ACCOUNT_ID]', redacted_text)
        
        # Redact phone numbers (after account IDs to avoid conflicts)
        for pattern in cls.PHONE_PATTERNS:
            redacted_text = pattern.sub('[REDACTED_PHONE]', redacted_text)
        
        # Redact usernames/handles
        redacted_text = cls.USERNAME_PATTERN.sub('[REDACTED_HANDLE]', redacted_text)
        
        return redacted_text
    
    @classmethod
    def has_pii(cls, text: str) -> bool:
        """Check if text contains PII"""
        if not text:
            return False
        
        # Check for any PII patterns
        if cls.EMAIL_PATTERN.search(text):
            return True
        
        for pattern in cls.PHONE_PATTERNS:
            if pattern.search(text):
                return True
        
        if cls.ACCOUNT_ID_PATTERN.search(text):
            return True
        
        if cls.USERNAME_PATTERN.search(text):
            return True
        
        return False


class TextCleaner:
    """Clean review text before processing"""
    
    # Emoji pattern for detection (before removal) - comprehensive Unicode ranges
    EMOJI_PATTERN = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F700-\U0001F77F"  # alchemical symbols
        "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
        "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs (includes 🥰)
        "\U0001FA00-\U0001FA6F"  # Chess Symbols
        "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"  # Dingbats
        "\U000024C2-\U0001F251"
        "\U00002600-\U000026FF"  # Miscellaneous Symbols
        "\U00002700-\U000027BF"  # Dingbats
        "]+", flags=re.UNICODE
    )
    
    @classmethod
    def has_emoji(cls, text: str) -> bool:
        """
        Check if text contains emojis using multiple methods for reliability
        """
        if not text:
            return False
        
        # Method 1: Use emoji library if available (most reliable)
        if EMOJI_LIB_AVAILABLE:
            return emoji.emoji_count(text) > 0
        
        # Method 2: Try regex pattern
        if cls.EMOJI_PATTERN.search(text):
            return True
        
        # Method 3: Check character-by-character for emoji Unicode ranges
        # This is more reliable for edge cases
        for char in text:
            code_point = ord(char)
            # Check various emoji ranges
            if (
                (0x1F600 <= code_point <= 0x1F64F) or  # emoticons
                (0x1F300 <= code_point <= 0x1F5FF) or  # symbols & pictographs
                (0x1F680 <= code_point <= 0x1F6FF) or  # transport & map symbols
                (0x1F700 <= code_point <= 0x1F77F) or  # alchemical symbols
                (0x1F780 <= code_point <= 0x1F7FF) or  # Geometric Shapes Extended
                (0x1F800 <= code_point <= 0x1F8FF) or  # Supplemental Arrows-C
                (0x1F900 <= code_point <= 0x1F9FF) or  # Supplemental Symbols and Pictographs
                (0x1FA00 <= code_point <= 0x1FA6F) or  # Chess Symbols
                (0x1FA70 <= code_point <= 0x1FAFF) or  # Symbols and Pictographs Extended-A
                (0x1F1E0 <= code_point <= 0x1F1FF) or  # flags
                (0x2702 <= code_point <= 0x27B0) or   # Dingbats
                (0x2600 <= code_point <= 0x26FF) or   # Miscellaneous Symbols
                (0x2700 <= code_point <= 0x27BF)      # Dingbats
            ):
                return True
        
        return False
    
    @staticmethod
    def clean(text: str) -> str:
        """
        Clean review text:
        - Remove HTML tags
        - Remove emojis
        - Normalize whitespace
        - Remove URLs
        - Remove excessive punctuation
        """
        if not text:
            return ""
        
        cleaned = text
        
        # Remove HTML tags
        cleaned = re.sub(r'<[^>]+>', '', cleaned)
        
        # Remove URLs
        url_pattern = re.compile(
            r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        )
        cleaned = url_pattern.sub('', cleaned)
        
        # Remove app-specific referral codes
        referral_pattern = re.compile(r'\b(?:ref|code|promo)[\s:]*\w+\b', re.IGNORECASE)
        cleaned = referral_pattern.sub('', cleaned)
        
        # Remove emojis
        cleaned = TextCleaner.EMOJI_PATTERN.sub('', cleaned)
        
        # Normalize whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        # Remove excessive punctuation (more than 3 consecutive)
        cleaned = re.sub(r'([!?.]){3,}', r'\1\1', cleaned)
        
        # Strip quotes and normalize
        cleaned = cleaned.strip().strip('"').strip("'")
        
        return cleaned


class LanguageDetector:
    """Detect if review text is semantically in English"""
    
    # Minimum confidence threshold for English detection
    MIN_ENGLISH_CONFIDENCE = 0.7
    
    # Languages to filter out (transliterated content)
    NON_ENGLISH_LANGUAGES = {'hi', 'mr', 'gu', 'ta', 'te', 'kn', 'ml', 'pa', 'bn', 'or', 'as'}
    
    @classmethod
    def is_english(cls, text: str) -> bool:
        """
        Check if text is semantically in English
        
        Args:
            text: Text to check
        
        Returns:
            True if text is semantically English, False otherwise
        """
        if not text or not text.strip():
            return False
        
        # First, check for Hindi transliteration patterns (most reliable for this use case)
        # This catches transliterated Hindi even when langdetect thinks it's English
        if not cls._simple_english_check(text):
            return False
        
        if not LANGDETECT_AVAILABLE:
            # If langdetect is not available, use simple heuristic result
            return True  # Already passed simple check above
        
        try:
            # Clean text for better detection
            cleaned_text = text.strip()
            
            # Skip very short texts (less reliable)
            if len(cleaned_text.split()) < 3:
                return True  # Allow short texts through
            
            # Detect language with confidence scores
            languages = detect_langs(cleaned_text)
            
            if not languages:
                return True  # If detection fails, allow through (already passed simple check)
            
            # Check if top detected language is English with sufficient confidence
            top_lang = languages[0]
            
            # If a non-English language is detected with high confidence, reject it
            if top_lang.lang in cls.NON_ENGLISH_LANGUAGES and top_lang.prob >= cls.MIN_ENGLISH_CONFIDENCE:
                return False
            
            # If English is detected with high confidence, accept it
            if top_lang.lang == 'en' and top_lang.prob >= cls.MIN_ENGLISH_CONFIDENCE:
                return True
            
            # If English is detected but with lower confidence, still accept (passed simple check)
            if top_lang.lang == 'en':
                return True
            
            # Check if English is in top languages
            for lang in languages[:2]:  # Check top 2 languages
                if lang.lang == 'en' and lang.prob >= 0.3:
                    return True
            
            # If no English detected but passed simple check, allow through
            # (might be mixed language or edge case)
            return True
            
        except LangDetectException:
            # If detection fails, use simple heuristic result (already passed)
            logger.debug(f"Language detection failed for text: {text[:50]}...")
            return True
        except Exception as e:
            logger.warning(f"Error in language detection: {e}")
            return True  # Default to allowing through if already passed simple check
    
    @classmethod
    def _simple_english_check(cls, text: str) -> bool:
        """
        Simple heuristic check for English (checks for Hindi transliteration patterns)
        
        Args:
            text: Text to check
        
        Returns:
            True if likely English, False if Hindi transliteration detected
        """
        if not text:
            return False
        
        text_lower = text.lower()
        
        # Common Hindi transliteration patterns (more comprehensive)
        hindi_patterns = [
            # Common Hindi words
            r'\b(?:nahin|nahi|nhi|kyun|kya|kaise|kab|kahan|kis|kisi|ko|se|mein|par|aur|ya|lekin|magar|agar|toh|to|bhi|hain|hai|ho|hoga|hogi|honge|tha|thi|the|raha|rahi|rahe|gaya|gayi|gaye|kar|ki|ke|ka)\b',
            # Common Hindi adjectives/adverbs
            r'\b(?:achha|accha|bahut|zyada|kam|sabse|sab|har|kuch|kuchh|bilkul|thoda|thodi|thode|bahar|andar|upar|neeche|aage|peeche|idhar|udhar|yahan|wahan)\b',
            # Common Hindi verbs
            r'\b(?:karo|kare|karte|karti|karne|kar|kiya|kiye|kiya|diya|diye|di|liya|liye|li|gaya|gaye|gayi|aaya|aaye|aayi|gaya|gaye|gayi|hoga|hogi|honge|hoga|hogi|honge)\b',
            # Common Hindi phrases/expressions
            r'\b(?:matlab|yaani|kyunki|isliye|tabhi|abhi|pehle|baad|mein|ke|liye|se|tak|bina)\b',
        ]
        
        hindi_word_count = 0
        
        for pattern in hindi_patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            hindi_word_count += len(matches)
        
        # Calculate word density
        words = text_lower.split()
        total_words = len(words)
        
        if total_words == 0:
            return False
        
        # If Hindi words make up significant portion, likely transliterated Hindi
        hindi_ratio = hindi_word_count / total_words if total_words > 0 else 0
        
        # Reject if: 3+ Hindi words OR Hindi words make up 30%+ of text
        if hindi_word_count >= 3 or hindi_ratio >= 0.3:
            return False
        
        # For very short texts, be more lenient
        if total_words <= 5:
            if hindi_word_count >= 2:
                return False
        
        return True


class ReviewValidator:
    """Validate review schema and data"""
    
    REQUIRED_FIELDS = ['review_id', 'title', 'text', 'date', 'platform']
    
    @classmethod
    def validate(cls, review_data: Dict) -> tuple[bool, Optional[str]]:
        """
        Validate review data structure
        
        Args:
            review_data: Review dictionary
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check required fields
        for field in cls.REQUIRED_FIELDS:
            if field not in review_data:
                return False, f"Missing required field: {field}"
        
        # Validate review_id
        if not isinstance(review_data['review_id'], str) or not review_data['review_id']:
            return False, "review_id must be a non-empty string"
        
        # Validate title
        if not isinstance(review_data['title'], str):
            return False, "title must be a string"
        
        # Validate text
        if not isinstance(review_data['text'], str):
            return False, "text must be a string"
        
        if len(review_data['text'].strip()) == 0:
            return False, "text cannot be empty"
        
        # Validate date
        if not isinstance(review_data['date'], datetime):
            return False, "date must be a datetime object"
        
        # Validate platform
        if review_data['platform'] not in ['app_store', 'play_store']:
            return False, "platform must be 'app_store' or 'play_store'"
        
        return True, None
    
    @classmethod
    def process_review(cls, review_data: Dict) -> Dict:
        """
        Process review: clean text, detect/redact PII, validate, check language
        
        Filters out reviews with:
        - Non-English text
        - Emojis
        - PII (Personally Identifiable Information)
        - Less than 20 characters after cleaning
        
        Args:
            review_data: Raw review dictionary
        
        Returns:
            Processed review dictionary, or None if review should be filtered out
        """
        original_text = review_data.get('text', '')
        original_title = review_data.get('title', '')
        review_id = review_data.get('review_id', 'unknown')
        
        # Filter 1: Check for emojis in original text (reject if found)
        if TextCleaner.has_emoji(original_text) or TextCleaner.has_emoji(original_title):
            logger.debug(f"Review filtered out (contains emojis): {review_id} - {original_text[:50]}...")
            return None
        
        # Filter 2: Check for PII in original text (reject if found)
        if PIIDetector.has_pii(original_text) or PIIDetector.has_pii(original_title):
            logger.debug(f"Review filtered out (contains PII): {review_id} - {original_text[:50]}...")
            return None
        
        # Clean text
        cleaned_text = TextCleaner.clean(original_text)
        cleaned_title = TextCleaner.clean(original_title)
        
        # Filter 3: Check length after cleaning (must be >= 20 characters)
        if len(cleaned_text.strip()) < 20:
            logger.debug(f"Review filtered out (less than 20 characters after cleaning): {review_id} - {cleaned_text[:50]}...")
            return None
        
        # Filter 4: Check if text is semantically English (filter out transliterated Hindi/other languages)
        if not LanguageDetector.is_english(cleaned_text):
            logger.debug(f"Review filtered out (not semantically English): {review_id} - {cleaned_text[:50]}...")
            return None
        
        # Update review data (text is already cleaned, no PII to redact since we filtered it out)
        processed_review = review_data.copy()
        processed_review['text'] = cleaned_text
        processed_review['title'] = cleaned_title
        
        # Validate
        is_valid, error = cls.validate(processed_review)
        if not is_valid:
            logger.warning(f"Review validation failed: {error}. Review ID: {review_id}")
            return None
        
        return processed_review
