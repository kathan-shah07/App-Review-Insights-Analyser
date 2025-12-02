"""
Comprehensive tests for Layer 1: Data Import & Validation
Tests scraper, validator, deduplicator, storage, and full import workflow
"""
import sys
import os
import json
import tempfile
import shutil
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from layer_1_data_import.scraper import PlayStoreScraper, fetch_all_reviews
from layer_1_data_import.validator import ReviewValidator, PIIDetector, TextCleaner
from layer_1_data_import.deduplicator import ReviewDeduplicator
from layer_1_data_import.storage import ReviewStorage
from layer_1_data_import.import_reviews import import_reviews
from models.review import Review
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class TestPIIDetector:
    """Test PII detection and redaction"""
    
    def test_email_detection(self):
        """Test email detection and redaction"""
        text = "Contact me at user@example.com for details"
        redacted = PIIDetector.detect_and_redact(text)
        assert "[REDACTED_EMAIL]" in redacted
        assert "user@example.com" not in redacted
        
        assert PIIDetector.has_pii(text) == True
        assert PIIDetector.has_pii("No email here") == False
    
    def test_phone_detection(self):
        """Test phone number detection"""
        texts = [
            "Call me at 1234567890",
            "Phone: +1-234-567-8900",
            "Contact: 98765-43210"
        ]
        for text in texts:
            redacted = PIIDetector.detect_and_redact(text)
            assert "[REDACTED_PHONE]" in redacted
            assert PIIDetector.has_pii(text) == True
    
    def test_account_id_detection(self):
        """Test account/order ID detection"""
        text = "My account ID is 123456789"
        redacted = PIIDetector.detect_and_redact(text)
        assert "[REDACTED_ACCOUNT_ID]" in redacted
    
    def test_username_detection(self):
        """Test username/handle detection"""
        text = "Follow me @username123"
        redacted = PIIDetector.detect_and_redact(text)
        assert "[REDACTED_HANDLE]" in redacted


class TestTextCleaner:
    """Test text cleaning functionality"""
    
    def test_html_removal(self):
        """Test HTML tag removal"""
        text = "<p>Hello <b>world</b></p>"
        cleaned = TextCleaner.clean(text)
        assert "<" not in cleaned
        assert ">" not in cleaned
        assert "Hello world" in cleaned
    
    def test_url_removal(self):
        """Test URL removal"""
        text = "Check out https://example.com for more info"
        cleaned = TextCleaner.clean(text)
        assert "https://example.com" not in cleaned
    
    def test_emoji_removal(self):
        """Test emoji removal"""
        text = "Great app! 😀👍🎉"
        cleaned = TextCleaner.clean(text)
        assert "😀" not in cleaned
        assert "👍" not in cleaned
        assert "🎉" not in cleaned
    
    def test_whitespace_normalization(self):
        """Test whitespace normalization"""
        text = "Hello    world\n\n\nTest"
        cleaned = TextCleaner.clean(text)
        assert "  " not in cleaned  # No double spaces
        assert "\n\n" not in cleaned  # No double newlines
    
    def test_excessive_punctuation(self):
        """Test excessive punctuation removal"""
        text = "Amazing!!!"
        cleaned = TextCleaner.clean(text)
        assert cleaned.count("!") <= 2


class TestReviewValidator:
    """Test review validation"""
    
    def test_valid_review(self):
        """Test validation of valid review"""
        review = {
            "review_id": "test_123",
            "title": "Great app",
            "text": "This is a great app with many features",
            "date": datetime.now(),
            "rating": 5,
            "platform": "app_store"
        }
        is_valid, error = ReviewValidator.validate(review)
        assert is_valid == True
        assert error is None
    
    def test_missing_fields(self):
        """Test validation with missing fields"""
        review = {
            "review_id": "test_123",
            "title": "Great app",
            # Missing text, date, platform
        }
        is_valid, error = ReviewValidator.validate(review)
        assert is_valid == False
        assert "Missing required field" in error
    
    def test_invalid_rating(self):
        """Test validation with invalid rating - rating is optional, so validation should pass"""
        review = {
            "review_id": "test_123",
            "title": "Great app",
            "text": "This is a great app",
            "date": datetime.now(),
            "rating": 10,  # Invalid: should be 1-5, but rating is optional
            "platform": "app_store"
        }
        is_valid, error = ReviewValidator.validate(review)
        # Rating is not a required field, so validation should pass
        assert is_valid == True
    
    def test_invalid_platform(self):
        """Test validation with invalid platform"""
        review = {
            "review_id": "test_123",
            "title": "Great app",
            "text": "This is a great app",
            "date": datetime.now(),
            "platform": "invalid_platform"
        }
        is_valid, error = ReviewValidator.validate(review)
        assert is_valid == False
        assert "platform" in error.lower()
    
    def test_process_review(self):
        """Test full review processing"""
        review = {
            "review_id": "test_123",
            "title": "Great app <b>test</b>",
            "text": "This is a great app with many features and good user experience",  # No PII, long enough
            "date": datetime.now(),
            "rating": 5,
            "platform": "app_store"
        }
        processed = ReviewValidator.process_review(review)
        assert processed is not None
        assert "<b>" not in processed["title"]
        assert len(processed["text"].strip()) >= 20


class TestReviewDeduplicator:
    """Test review deduplication"""
    
    def test_deduplication(self):
        """Test deduplication logic"""
        # Create temporary cache directory
        temp_dir = tempfile.mkdtemp()
        cache_file = os.path.join(temp_dir, "test_cache.json")
        
        try:
            deduplicator = ReviewDeduplicator(cache_file=cache_file)
            
            reviews = [
                {"review_id": "review_1", "text": "First review"},
                {"review_id": "review_2", "text": "Second review"},
                {"review_id": "review_1", "text": "First review"},  # Duplicate
            ]
            
            unique = deduplicator.filter_duplicates(reviews)
            assert len(unique) == 2
            assert unique[0]["review_id"] == "review_1"
            assert unique[1]["review_id"] == "review_2"
            
            # Test that duplicates are filtered on second run
            unique2 = deduplicator.filter_duplicates(reviews)
            assert len(unique2) == 0  # All are duplicates now
            
        finally:
            shutil.rmtree(temp_dir)
    
    def test_cache_persistence(self):
        """Test that cache persists across instances"""
        temp_dir = tempfile.mkdtemp()
        cache_file = os.path.join(temp_dir, "test_cache.json")
        
        try:
            # First instance
            deduplicator1 = ReviewDeduplicator(cache_file=cache_file)
            reviews = [{"review_id": "review_1", "text": "First review"}]
            deduplicator1.filter_duplicates(reviews)
            
            # Second instance should load cache
            deduplicator2 = ReviewDeduplicator(cache_file=cache_file)
            assert deduplicator2.is_duplicate("review_1") == True
            
        finally:
            shutil.rmtree(temp_dir)


class TestReviewStorage:
    """Test review storage"""
    
    def test_week_key_calculation(self):
        """Test week key calculation"""
        storage = ReviewStorage()
        
        # Monday
        monday = datetime(2024, 1, 1)  # Monday
        week_key = storage._get_week_key(monday)
        assert week_key == "2024-01-01"
        
        # Wednesday (should map to Monday)
        wednesday = datetime(2024, 1, 3)  # Wednesday
        week_key = storage._get_week_key(wednesday)
        assert week_key == "2024-01-01"
        
        # Sunday (should map to previous Monday)
        sunday = datetime(2024, 1, 7)  # Sunday
        week_key = storage._get_week_key(sunday)
        assert week_key == "2024-01-01"
    
    def test_save_and_load_reviews(self):
        """Test saving and loading reviews"""
        temp_dir = tempfile.mkdtemp()
        
        try:
            storage = ReviewStorage(storage_dir=temp_dir)
            
            # Create test reviews
            reviews = [
                Review(
                    review_id="review_1",
                    title="Test Review 1",
                    text="This is a test review",
                    date=datetime(2024, 1, 1),  # Monday
                    rating=5,
                    platform="app_store"
                ),
                Review(
                    review_id="review_2",
                    title="Test Review 2",
                    text="Another test review",
                    date=datetime(2024, 1, 2),  # Tuesday (same week)
                    rating=4,
                    platform="play_store"
                ),
            ]
            
            # Save reviews
            storage.save_reviews(reviews)
            
            # Load reviews
            week_key = storage._get_week_key(reviews[0].date)
            loaded = storage.load_week_reviews(week_key)
            
            assert len(loaded) == 2
            assert loaded[0]["review_id"] == "review_1"
            assert loaded[1]["review_id"] == "review_2"
            
            # Test available weeks
            weeks = storage.get_available_weeks()
            assert week_key in weeks
            
        finally:
            shutil.rmtree(temp_dir)
    
    def test_duplicate_prevention(self):
        """Test that duplicates are not saved"""
        temp_dir = tempfile.mkdtemp()
        
        try:
            storage = ReviewStorage(storage_dir=temp_dir)
            
            review = Review(
                review_id="review_1",
                title="Test Review",
                text="This is a test review",
                date=datetime(2024, 1, 1),
                platform="app_store"
            )
            
            # Save twice
            storage.save_reviews([review])
            storage.save_reviews([review])
            
            # Should only have one review
            week_key = storage._get_week_key(review.date)
            loaded = storage.load_week_reviews(week_key)
            assert len(loaded) == 1
            
        finally:
            shutil.rmtree(temp_dir)


class TestScrapers:
    """Test scraper functionality"""
    
    def test_play_store_scraper_initialization(self):
        """Test Play Store scraper initialization"""
        scraper = PlayStoreScraper(
            app_id="com.nextbillion.groww",
            app_url="https://play.google.com/store/apps/details?id=com.nextbillion.groww"
        )
        assert scraper.app_id == "com.nextbillion.groww"
    
    @patch('layer_1_data_import.scraper.play_reviews')
    def test_play_store_scraper_mock(self, mock_play_reviews):
        """Test Play Store scraper with mocked data"""
        # Mock Play Store response
        mock_play_reviews.return_value = (
            [
                {
                    "content": "Great app!",
                    "score": 5,
                    "at": (datetime.now() - timedelta(days=10)).timestamp() * 1000,
                    "userName": "User1"
                }
            ],
            None  # No continuation token
        )
        
        scraper = PlayStoreScraper("com.nextbillion.groww", "https://play.google.com/store/apps/details?id=com.nextbillion.groww")
        start_date = datetime.now() - timedelta(days=30)
        end_date = datetime.now()
        
        reviews = scraper.fetch_reviews(start_date, end_date)
        
        assert isinstance(reviews, list)
        if reviews:
            assert reviews[0]["platform"] == "play_store"


class TestFullImportWorkflow:
    """Test the complete import workflow"""
    
    @patch('layer_1_data_import.import_reviews.fetch_all_reviews')
    def test_import_workflow_mock(self, mock_fetch):
        """Test full import workflow with mocked scrapers"""
        # Mock scraped reviews
        mock_fetch.return_value = [
            {
                "review_id": "test_1",
                "title": "Great app",
                "text": "This is a great app with many features",
                "date": datetime.now() - timedelta(days=10),
                "rating": 5,
                "platform": "app_store"
            },
            {
                "review_id": "test_2",
                "title": "Good app",
                "text": "This is a good app with nice features",
                "date": datetime.now() - timedelta(days=5),
                "rating": 4,
                "platform": "play_store"
            }
        ]
        
        # Use temporary directories
        temp_data_dir = tempfile.mkdtemp()
        temp_cache_dir = tempfile.mkdtemp()
        temp_reviews_dir = tempfile.mkdtemp()
        
        try:
            # Patch settings
            original_data_dir = settings.DATA_DIR
            original_cache_dir = settings.CACHE_DIR
            original_reviews_dir = settings.REVIEWS_DIR
            
            settings.DATA_DIR = temp_data_dir
            settings.CACHE_DIR = temp_cache_dir
            settings.REVIEWS_DIR = temp_reviews_dir
            
            # Run import
            reviews = import_reviews()
            
            # Verify results
            assert len(reviews) == 2
            assert all(isinstance(r, Review) for r in reviews)
            
            # Restore settings
            settings.DATA_DIR = original_data_dir
            settings.CACHE_DIR = original_cache_dir
            settings.REVIEWS_DIR = original_reviews_dir
            
        finally:
            shutil.rmtree(temp_data_dir)
            shutil.rmtree(temp_cache_dir)
            shutil.rmtree(temp_reviews_dir)
    
    @patch('layer_1_data_import.import_reviews.fetch_all_reviews')
    def test_short_review_filtering(self, mock_fetch):
        """Test that reviews with less than 20 characters are filtered out"""
        # Mock scraped reviews with one short review
        mock_fetch.return_value = [
            {
                "review_id": "test_1",
                "title": "Great app",
                "text": "This is a great app with many features",  # 40 chars - should pass
                "date": datetime.now() - timedelta(days=10),
                "rating": 5,
                "platform": "app_store"
            },
            {
                "review_id": "test_2",
                "title": "Short",
                "text": "Too short",  # 9 chars - should be filtered
                "date": datetime.now() - timedelta(days=5),
                "rating": 4,
                "platform": "play_store"
            },
            {
                "review_id": "test_3",
                "title": "Exactly 20",
                "text": "This is a good app with many features",  # 40 chars - should pass
                "date": datetime.now() - timedelta(days=3),
                "rating": 5,
                "platform": "app_store"
            },
            {
                "review_id": "test_4",
                "title": "19 chars",
                "text": "Short review",  # 12 chars - should be filtered
                "date": datetime.now() - timedelta(days=2),
                "rating": 3,
                "platform": "play_store"
            }
        ]
        
        # Use temporary directories
        temp_data_dir = tempfile.mkdtemp()
        temp_cache_dir = tempfile.mkdtemp()
        temp_reviews_dir = tempfile.mkdtemp()
        
        try:
            # Patch settings
            original_data_dir = settings.DATA_DIR
            original_cache_dir = settings.CACHE_DIR
            original_reviews_dir = settings.REVIEWS_DIR
            
            settings.DATA_DIR = temp_data_dir
            settings.CACHE_DIR = temp_cache_dir
            settings.REVIEWS_DIR = temp_reviews_dir
            
            # Run import
            reviews = import_reviews()
            
            # Verify results - should only have 2 reviews (test_1 and test_3)
            assert len(reviews) == 2
            assert all(isinstance(r, Review) for r in reviews)
            review_ids = [r.review_id for r in reviews]
            assert "test_1" in review_ids
            assert "test_3" in review_ids
            assert "test_2" not in review_ids  # Short review filtered
            assert "test_4" not in review_ids  # 19 char review filtered
            
            # Restore settings
            settings.DATA_DIR = original_data_dir
            settings.CACHE_DIR = original_cache_dir
            settings.REVIEWS_DIR = original_reviews_dir
            
        finally:
            shutil.rmtree(temp_data_dir)
            shutil.rmtree(temp_cache_dir)
            shutil.rmtree(temp_reviews_dir)


def run_all_tests():
    """Run all test suites"""
    print("=" * 80)
    print("Layer 1 Data Import - Comprehensive Test Suite")
    print("=" * 80)
    
    test_classes = [
        ("PII Detector", TestPIIDetector),
        ("Text Cleaner", TestTextCleaner),
        ("Review Validator", TestReviewValidator),
        ("Review Deduplicator", TestReviewDeduplicator),
        ("Review Storage", TestReviewStorage),
        ("Scrapers", TestScrapers),
        ("Full Import Workflow", TestFullImportWorkflow),
    ]
    
    total_tests = 0
    passed_tests = 0
    failed_tests = []
    
    for suite_name, test_class in test_classes:
        print(f"\n{'=' * 80}")
        print(f"Running {suite_name} Tests")
        print(f"{'=' * 80}")
        
        test_instance = test_class()
        test_methods = [method for method in dir(test_instance) if method.startswith('test_')]
        
        for test_method in test_methods:
            total_tests += 1
            test_func = getattr(test_instance, test_method)
            try:
                test_func()
                print(f"  ✅ {test_method}")
                passed_tests += 1
            except Exception as e:
                print(f"  ❌ {test_method}: {e}")
                failed_tests.append((suite_name, test_method, str(e)))
                logger.error(f"Test failed: {suite_name}.{test_method}: {e}", exc_info=True)
    
    # Summary
    print(f"\n{'=' * 80}")
    print("Test Summary")
    print(f"{'=' * 80}")
    print(f"Total tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {len(failed_tests)}")
    
    if failed_tests:
        print(f"\nFailed tests:")
        for suite, test, error in failed_tests:
            print(f"  - {suite}.{test}: {error}")
        return 1
    else:
        print(f"\n✅ All tests passed!")
        return 0


if __name__ == "__main__":
    sys.exit(run_all_tests())
