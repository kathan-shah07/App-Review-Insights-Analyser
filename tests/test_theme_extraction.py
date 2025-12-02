"""
Comprehensive unit tests for Layer 2: Theme Extraction & Classification
Tests theme config, classifier, weekly processor, and batching logic
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

from layer_2_theme_extraction.theme_config import (
    THEMES,
    get_theme_list,
    get_theme_description,
    is_valid_theme,
    get_fallback_theme,
    get_all_theme_descriptions,
    MIN_REVIEW_LENGTH
)
from layer_2_theme_extraction.classifier import (
    ReviewClassifier,
    aggregate_theme_counts,
    get_top_themes_by_count,
    REVIEWS_PER_BATCH
)
from layer_2_theme_extraction.weekly_processor import WeeklyThemeProcessor
from layer_1_data_import.storage import ReviewStorage
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class TestThemeConfig:
    """Test theme configuration"""
    
    def test_get_theme_list(self):
        """Test getting list of themes"""
        themes = get_theme_list()
        assert isinstance(themes, list)
        assert len(themes) == 5
        assert "Trading Experience" in themes
        assert "Mutual Funds & SIP Experience" in themes
        assert "Payments, UPI & Settlements" in themes
        assert "App Performance & Reliability" in themes
        assert "Support & Service Quality" in themes
    
    def test_get_theme_description(self):
        """Test getting theme description"""
        desc = get_theme_description("Trading Experience")
        assert isinstance(desc, str)
        assert len(desc) > 0
        assert "order" in desc.lower() or "trading" in desc.lower()
        
        # Test non-existent theme
        desc = get_theme_description("Non-existent Theme")
        assert desc == ""
    
    def test_is_valid_theme(self):
        """Test theme validation"""
        assert is_valid_theme("Trading Experience") == True
        assert is_valid_theme("App Performance & Reliability") == True
        assert is_valid_theme("Invalid Theme") == False
        assert is_valid_theme("") == False
    
    def test_get_fallback_theme(self):
        """Test fallback theme"""
        fallback = get_fallback_theme()
        assert isinstance(fallback, str)
        assert is_valid_theme(fallback) == True
        assert fallback == "App Performance & Reliability"
    
    def test_get_all_theme_descriptions(self):
        """Test getting all theme descriptions"""
        descriptions = get_all_theme_descriptions()
        assert isinstance(descriptions, dict)
        assert len(descriptions) == 5
        assert "Trading Experience" in descriptions
        assert isinstance(descriptions["Trading Experience"], str)
    
    def test_min_review_length(self):
        """Test minimum review length constant"""
        assert MIN_REVIEW_LENGTH == 20
        assert isinstance(MIN_REVIEW_LENGTH, int)


class TestReviewClassifier:
    """Test review classifier with mocked LLM"""
    
    def test_classifier_initialization(self):
        """Test classifier initialization"""
        with patch('layer_2_theme_extraction.classifier.LLMClient'):
            classifier = ReviewClassifier()
            assert classifier.themes is not None
            assert len(classifier.themes) == 5
            assert classifier.fallback_theme == "App Performance & Reliability"
    
    def test_batching_logic(self):
        """Test that reviews are batched correctly"""
        with patch('layer_2_theme_extraction.classifier.LLMClient'):
            classifier = ReviewClassifier()
            
            # Create 250 reviews (to test batching with batch size 100)
            reviews = [
                {
                    "review_id": f"review_{i}",
                    "text": f"This is review number {i} with enough characters to pass validation" * 2
                }
                for i in range(250)
            ]
            
            # Mock the LLM client
            mock_llm = Mock()
            mock_llm.generate.return_value = json.dumps([
                {
                    "review_id": f"review_{i}",
                    "chosen_theme": "Trading Experience",
                    "short_reason": "Test reason"
                }
                for i in range(100)  # Mock response for first batch
            ])
            classifier.llm_client = mock_llm
            
            # Mock the classify_batch_with_retry to avoid actual API calls
            with patch.object(classifier, '_classify_batch_with_retry') as mock_retry:
                mock_retry.return_value = [
                    {
                        "review_id": f"review_{i}",
                        "chosen_theme": "Trading Experience",
                        "short_reason": "Test reason"
                    }
                    for i in range(100)
                ]
                
                # This will test the batching logic
                result = classifier.classify_batch(reviews, "test_batch")
                
                # Should be called 3 times (250 reviews / 100 = 3 batches, with last batch having 50)
                assert mock_retry.call_count == 3
    
    def test_short_review_filtering(self):
        """Test that short reviews are filtered out"""
        with patch('layer_2_theme_extraction.classifier.LLMClient'):
            classifier = ReviewClassifier()
            
            reviews = [
                {"review_id": "review_1", "text": "Short"},  # < 20 chars
                {"review_id": "review_2", "text": "This is a longer review with enough characters"},  # >= 20 chars
                {"review_id": "review_3", "text": "Also short"},  # < 20 chars
            ]
            
            with patch.object(classifier, '_classify_batch_with_retry') as mock_retry:
                mock_retry.return_value = [
                    {
                        "review_id": "review_2",
                        "chosen_theme": "Trading Experience",
                        "short_reason": "Test reason"
                    }
                ]
                
                result = classifier.classify_batch(reviews, "test")
                
                # Should only process 1 review (the long one)
                assert len(result) == 1
                assert result[0]["review_id"] == "review_2"
    
    def test_aggregate_theme_counts(self):
        """Test theme count aggregation"""
        classifications = [
            {"review_id": "1", "chosen_theme": "Trading Experience", "short_reason": "Reason 1"},
            {"review_id": "2", "chosen_theme": "Trading Experience", "short_reason": "Reason 2"},
            {"review_id": "3", "chosen_theme": "App Performance & Reliability", "short_reason": "Reason 3"},
            {"review_id": "4", "chosen_theme": "Trading Experience", "short_reason": "Reason 4"},
        ]
        
        counts = aggregate_theme_counts(classifications)
        
        assert counts["Trading Experience"] == 3
        assert counts["App Performance & Reliability"] == 1
        assert len(counts) == 2
    
    def test_get_top_themes_by_count(self):
        """Test getting top themes by count"""
        classifications = [
            {"review_id": "1", "chosen_theme": "Theme A", "short_reason": "Reason"},
            {"review_id": "2", "chosen_theme": "Theme A", "short_reason": "Reason"},
            {"review_id": "3", "chosen_theme": "Theme A", "short_reason": "Reason"},
            {"review_id": "4", "chosen_theme": "Theme B", "short_reason": "Reason"},
            {"review_id": "5", "chosen_theme": "Theme B", "short_reason": "Reason"},
            {"review_id": "6", "chosen_theme": "Theme C", "short_reason": "Reason"},
        ]
        
        top_themes = get_top_themes_by_count(classifications, max_themes=2)
        
        assert len(top_themes) == 2
        assert top_themes[0][0] == "Theme A"
        assert top_themes[0][1] == 3
        assert top_themes[1][0] == "Theme B"
        assert top_themes[1][1] == 2
    
    def test_parse_llm_response_json(self):
        """Test parsing JSON response from LLM"""
        with patch('layer_2_theme_extraction.classifier.LLMClient'):
            classifier = ReviewClassifier()
            
            reviews = [
                {"review_id": "review_1", "text": "This is a test review with enough characters"},
                {"review_id": "review_2", "text": "Another test review with sufficient length"}
            ]
            
            json_response = json.dumps([
                {
                    "review_id": "review_1",
                    "chosen_theme": "Trading Experience",
                    "short_reason": "Mentions trading"
                },
                {
                    "review_id": "review_2",
                    "chosen_theme": "App Performance & Reliability",
                    "short_reason": "Mentions performance"
                }
            ])
            
            parsed = classifier._parse_llm_response(json_response, reviews)
            
            assert len(parsed) == 2
            assert parsed[0]["review_id"] == "review_1"
            assert parsed[0]["chosen_theme"] == "Trading Experience"
            assert parsed[1]["review_id"] == "review_2"
            assert parsed[1]["chosen_theme"] == "App Performance & Reliability"
    
    def test_validate_classifications(self):
        """Test classification validation and guardrails"""
        with patch('layer_2_theme_extraction.classifier.LLMClient'):
            classifier = ReviewClassifier()
            
            reviews = [
                {"review_id": "review_1", "text": "Test review"},
                {"review_id": "review_2", "text": "Another review"}
            ]
            
            classifications = [
                {
                    "review_id": "review_1",
                    "chosen_theme": "Invalid Theme",  # Invalid theme
                    "short_reason": "Some reason"
                },
                {
                    "review_id": "review_2",
                    "chosen_theme": "Trading Experience",  # Valid theme
                    "short_reason": "Some reason"
                }
            ]
            
            validated = classifier._validate_classifications(classifications, reviews)
            
            assert len(validated) == 2
            # Invalid theme should be replaced with fallback
            assert validated[0]["chosen_theme"] == "App Performance & Reliability"
            assert validated[1]["chosen_theme"] == "Trading Experience"


class TestWeeklyThemeProcessor:
    """Test weekly theme processor"""
    
    def test_process_week(self):
        """Test processing a single week"""
        temp_dir = tempfile.mkdtemp()
        temp_reviews_dir = os.path.join(temp_dir, "reviews")
        temp_themes_dir = os.path.join(temp_dir, "themes")
        os.makedirs(temp_reviews_dir, exist_ok=True)
        os.makedirs(temp_themes_dir, exist_ok=True)
        
        try:
            # Create test reviews file
            week_key = "2024-01-01"
            reviews_file = os.path.join(temp_reviews_dir, f"reviews_{week_key}.json")
            
            test_reviews = [
                {
                    "review_id": f"review_{i}",
                    "text": f"This is test review number {i} with enough characters to pass validation" * 2,
                    "date": "2024-01-01T12:00:00",
                    "platform": "play_store"
                }
                for i in range(5)
            ]
            
            week_data = {
                "week_start_date": week_key,
                "week_end_date": "2024-01-07",
                "total_reviews": len(test_reviews),
                "reviews": test_reviews
            }
            
            with open(reviews_file, 'w', encoding='utf-8') as f:
                json.dump(week_data, f, indent=2)
            
            # Create storage and processor with temp directories
            storage = ReviewStorage(storage_dir=temp_reviews_dir)
            
            with patch('layer_2_theme_extraction.weekly_processor.settings') as mock_settings:
                mock_settings.THEMES_DIR = temp_themes_dir
                mock_settings.MAX_REVIEWS_PER_WEEK = 0  # Set to 0 to disable limit
                
                processor = WeeklyThemeProcessor(storage=storage)
                
                # Mock the classifier
                with patch.object(processor.classifier, 'classify_batch') as mock_classify:
                    mock_classify.return_value = [
                        {
                            "review_id": f"review_{i}",
                            "chosen_theme": "Trading Experience",
                            "short_reason": "Test reason"
                        }
                        for i in range(5)
                    ]
                    
                    result = processor.process_week(week_key)
                    
                    assert result["week_key"] == week_key
                    assert result["total_reviews"] == 5
                    assert result["classified_reviews"] == 5
                    assert "Trading Experience" in result["theme_counts"]
                    assert result["theme_counts"]["Trading Experience"] == 5
                    
                    # Check that theme file was created
                    theme_file = os.path.join(temp_themes_dir, f"themes_{week_key}.json")
                    assert os.path.exists(theme_file)
                    
                    # Verify file contents
                    with open(theme_file, 'r', encoding='utf-8') as f:
                        theme_data = json.load(f)
                        assert theme_data["week_key"] == week_key
                        assert len(theme_data["reviews"]) == 5
        
        finally:
            shutil.rmtree(temp_dir)
    
    def test_process_week_empty(self):
        """Test processing week with no reviews"""
        temp_dir = tempfile.mkdtemp()
        temp_reviews_dir = os.path.join(temp_dir, "reviews")
        os.makedirs(temp_reviews_dir, exist_ok=True)
        
        try:
            storage = ReviewStorage(storage_dir=temp_reviews_dir)
            processor = WeeklyThemeProcessor(storage=storage)
            
            result = processor.process_week("2024-01-01")
            
            assert result["week_key"] == "2024-01-01"
            assert result["total_reviews"] == 0
            assert result["classified_reviews"] == 0
            assert result["theme_counts"] == {}
        
        finally:
            shutil.rmtree(temp_dir)
    
    def test_enrich_reviews_with_themes(self):
        """Test enriching reviews with theme assignments"""
        temp_dir = tempfile.mkdtemp()
        
        try:
            processor = WeeklyThemeProcessor()
            
            reviews = [
                {"review_id": "review_1", "text": "Review 1"},
                {"review_id": "review_2", "text": "Review 2"},
                {"review_id": "review_3", "text": "Review 3"}
            ]
            
            classifications = [
                {"review_id": "review_1", "chosen_theme": "Trading Experience", "short_reason": "Reason 1"},
                {"review_id": "review_2", "chosen_theme": "App Performance & Reliability", "short_reason": "Reason 2"},
                # review_3 has no classification
            ]
            
            enriched = processor._enrich_reviews_with_themes(reviews, classifications)
            
            assert len(enriched) == 3
            assert enriched[0]["theme"] == "Trading Experience"
            assert enriched[0]["theme_reason"] == "Reason 1"
            assert enriched[1]["theme"] == "App Performance & Reliability"
            assert enriched[1]["theme_reason"] == "Reason 2"
            assert enriched[2]["theme"] is None  # No classification for review_3
            assert enriched[2]["theme_reason"] is None
        
        finally:
            shutil.rmtree(temp_dir)


class TestBatchingAndRetry:
    """Test batching and retry logic"""
    
    def test_reviews_per_batch_constant(self):
        """Test that REVIEWS_PER_BATCH is set correctly"""
        assert REVIEWS_PER_BATCH == 100
        assert isinstance(REVIEWS_PER_BATCH, int)
    
    def test_batch_splitting(self):
        """Test that reviews are split into correct batch sizes"""
        with patch('layer_2_theme_extraction.classifier.LLMClient'):
            classifier = ReviewClassifier()
            
            # Create 250 reviews (to test batching with batch size 100)
            reviews = [
                {
                    "review_id": f"review_{i}",
                    "text": f"This is review {i} with enough characters" * 3
                }
                for i in range(250)
            ]
            
            # Mock the retry method
            with patch.object(classifier, '_classify_batch_with_retry') as mock_retry:
                mock_retry.return_value = [
                    {"review_id": f"review_{i}", "chosen_theme": "Trading Experience", "short_reason": "Test"}
                    for i in range(100)
                ]
                
                result = classifier.classify_batch(reviews, "test")
                
                # Should be called 3 times (250 / 100 = 3 batches, with last batch having 50)
                assert mock_retry.call_count == 3
                
                # Check batch sizes
                call_args_list = mock_retry.call_args_list
                assert len(call_args_list[0][0][0]) == 100  # First batch: 100 reviews
                assert len(call_args_list[1][0][0]) == 100  # Second batch: 100 reviews
                assert len(call_args_list[2][0][0]) == 50   # Third batch: 50 reviews


def run_all_tests():
    """Run all test suites"""
    print("=" * 80)
    print("Layer 2 Theme Extraction - Comprehensive Test Suite")
    print("=" * 80)
    
    test_classes = [
        ("Theme Config", TestThemeConfig),
        ("Review Classifier", TestReviewClassifier),
        ("Weekly Theme Processor", TestWeeklyThemeProcessor),
        ("Batching and Retry", TestBatchingAndRetry),
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

