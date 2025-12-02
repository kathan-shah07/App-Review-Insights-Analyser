"""
Comprehensive unit tests for Layer 3: Content Generation
Tests theme summarizer, pulse assembler, and weekly pulse generator
"""
import sys
import os
import json
import tempfile
import shutil
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from layer_3_content_generation.theme_summarizer import ThemeSummarizer, REVIEWS_PER_CHUNK
from layer_3_content_generation.pulse_assembler import PulseAssembler, MAX_WORD_COUNT
from layer_3_content_generation.weekly_pulse_generator import WeeklyPulseGenerator
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class TestThemeSummarizer:
    """Test theme summarizer"""
    
    def test_initialization(self):
        """Test summarizer initialization"""
        with patch('layer_3_content_generation.theme_summarizer.LLMClient'):
            summarizer = ThemeSummarizer()
            assert summarizer.llm_client is not None
    
    def test_summarize_theme_empty(self):
        """Test summarizing theme with no reviews"""
        with patch('layer_3_content_generation.theme_summarizer.LLMClient'):
            summarizer = ThemeSummarizer()
            result = summarizer.summarize_theme("Test Theme", [])
            
            assert result["theme"] == "Test Theme"
            assert result["key_points"] == []
            assert result["candidate_quotes"] == []
    
    def test_chunking_logic(self):
        """Test that reviews are chunked correctly"""
        with patch('layer_3_content_generation.theme_summarizer.LLMClient'):
            summarizer = ThemeSummarizer()
            
            # Create 90 reviews (to test chunking with chunk size 30)
            reviews = [
                {
                    "review_id": f"review_{i}",
                    "text": f"This is review number {i} with enough characters to pass validation" * 2
                }
                for i in range(90)
            ]
            
            # Mock the chunk summarization
            with patch.object(summarizer, '_summarize_chunk') as mock_chunk:
                mock_chunk.return_value = {
                    "theme": "Test Theme",
                    "key_points": ["Point 1", "Point 2"],
                    "candidate_quotes": ["Quote 1", "Quote 2"]
                }
                
                result = summarizer.summarize_theme("Test Theme", reviews)
                
                # Should be called 3 times (90 / 30 = 3 chunks)
                assert mock_chunk.call_count == 3
                
                # Check chunk sizes
                call_args_list = mock_chunk.call_args_list
                assert len(call_args_list[0][0][1]) == 30  # First chunk: 30 reviews
                assert len(call_args_list[1][0][1]) == 30  # Second chunk: 30 reviews
                assert len(call_args_list[2][0][1]) == 30  # Third chunk: 30 reviews
    
    def test_parse_summarization_response(self):
        """Test parsing LLM response"""
        with patch('layer_3_content_generation.theme_summarizer.LLMClient'):
            summarizer = ThemeSummarizer()
            
            json_response = json.dumps({
                "theme": "Trading Experience",
                "key_points": [
                    "Users appreciate ease of use",
                    "Chart functionality needs improvement"
                ],
                "candidate_quotes": [
                    "Great app for trading",
                    "Charts are slow"
                ]
            })
            
            result = summarizer._parse_summarization_response(json_response, "Trading Experience")
            
            assert result is not None
            assert result["theme"] == "Trading Experience"
            assert len(result["key_points"]) == 2
            assert len(result["candidate_quotes"]) == 2
    
    def test_parse_summarization_response_markdown(self):
        """Test parsing LLM response with markdown code blocks"""
        with patch('layer_3_content_generation.theme_summarizer.LLMClient'):
            summarizer = ThemeSummarizer()
            
            json_response = "```json\n" + json.dumps({
                "theme": "Trading Experience",
                "key_points": ["Point 1"],
                "candidate_quotes": ["Quote 1"]
            }) + "\n```"
            
            result = summarizer._parse_summarization_response(json_response, "Trading Experience")
            
            assert result is not None
            assert result["theme"] == "Trading Experience"
    
    def test_reviews_per_chunk_constant(self):
        """Test that REVIEWS_PER_CHUNK is set correctly"""
        assert REVIEWS_PER_CHUNK == 30
        assert isinstance(REVIEWS_PER_CHUNK, int)
    
    def test_deduplication(self):
        """Test that duplicate key points and quotes are removed"""
        with patch('layer_3_content_generation.theme_summarizer.LLMClient'):
            summarizer = ThemeSummarizer()
            
            reviews = [
                {"review_id": f"review_{i}", "text": f"Review {i} with enough characters" * 3}
                for i in range(25)
            ]
            
            # Mock chunk responses with duplicates
            with patch.object(summarizer, '_summarize_chunk') as mock_chunk:
                mock_chunk.return_value = {
                    "theme": "Test Theme",
                    "key_points": ["Point 1", "Point 2", "Point 1"],  # Duplicate
                    "candidate_quotes": ["Quote 1", "Quote 2", "Quote 1"]  # Duplicate
                }
                
                result = summarizer.summarize_theme("Test Theme", reviews)
                
                # Should deduplicate
                assert len(result["key_points"]) <= 2  # After deduplication
                assert len(result["candidate_quotes"]) <= 2


class TestPulseAssembler:
    """Test pulse assembler"""
    
    def test_initialization(self):
        """Test assembler initialization"""
        with patch('layer_3_content_generation.pulse_assembler.LLMClient'):
            assembler = PulseAssembler()
            assert assembler.llm_client is not None
    
    def test_max_word_count_constant(self):
        """Test that MAX_WORD_COUNT is set correctly"""
        assert MAX_WORD_COUNT == 250
        assert isinstance(MAX_WORD_COUNT, int)
    
    def test_count_words(self):
        """Test word counting"""
        with patch('layer_3_content_generation.pulse_assembler.LLMClient'):
            assembler = PulseAssembler()
            
            pulse = {
                "title": "Test Title",
                "overview": "This is a test overview with multiple words",
                "themes": [
                    {"name": "Theme 1", "summary": "Summary for theme one"},
                    {"name": "Theme 2", "summary": "Summary for theme two"}
                ],
                "quotes": ["Quote one", "Quote two"],
                "actions": ["Action one", "Action two"]
            }
            
            word_count = assembler._count_words(pulse)
            assert word_count > 0
            assert isinstance(word_count, int)
    
    def test_parse_pulse_response(self):
        """Test parsing LLM pulse response"""
        with patch('layer_3_content_generation.pulse_assembler.LLMClient'):
            assembler = PulseAssembler()
            
            json_response = json.dumps({
                "title": "Weekly Pulse",
                "overview": "This week's overview",
                "themes": [
                    {"name": "Theme 1", "summary": "Summary 1"},
                    {"name": "Theme 2", "summary": "Summary 2"},
                    {"name": "Theme 3", "summary": "Summary 3"}
                ],
                "quotes": ["Quote 1", "Quote 2", "Quote 3"],
                "actions": ["Action 1", "Action 2", "Action 3"]
            })
            
            result = assembler._parse_pulse_response(json_response)
            
            assert result is not None
            assert result["title"] == "Weekly Pulse"
            assert len(result["themes"]) == 3
            assert len(result["quotes"]) == 3
            assert len(result["actions"]) == 3
    
    def test_parse_pulse_response_markdown(self):
        """Test parsing LLM response with markdown"""
        with patch('layer_3_content_generation.pulse_assembler.LLMClient'):
            assembler = PulseAssembler()
            
            json_response = "```json\n" + json.dumps({
                "title": "Weekly Pulse",
                "overview": "Overview",
                "themes": [{"name": "Theme 1", "summary": "Summary"}],
                "quotes": ["Quote 1"],
                "actions": ["Action 1"]
            }) + "\n```"
            
            result = assembler._parse_pulse_response(json_response)
            
            assert result is not None
            assert result["title"] == "Weekly Pulse"
    
    def test_enforce_word_limit_within_limit(self):
        """Test word limit enforcement when within limit"""
        with patch('layer_3_content_generation.pulse_assembler.LLMClient'):
            assembler = PulseAssembler()
            
            pulse = {
                "title": "Short Title",
                "overview": "Short overview",
                "themes": [
                    {"name": "Theme 1", "summary": "Short summary"}
                ],
                "quotes": ["Short quote"],
                "actions": ["Short action"]
            }
            
            result = assembler._enforce_word_limit(pulse)
            
            # Should return unchanged if within limit
            assert result == pulse
    
    def test_manual_truncate(self):
        """Test manual truncation fallback"""
        with patch('layer_3_content_generation.pulse_assembler.LLMClient'):
            assembler = PulseAssembler()
            
            pulse = {
                "title": "Test Title",
                "overview": " ".join(["word"] * 100),  # Long overview
                "themes": [
                    {"name": "Theme 1", "summary": " ".join(["word"] * 50)}  # Long summary
                ],
                "quotes": [" ".join(["word"] * 50)] * 3,
                "actions": [" ".join(["word"] * 50)] * 3
            }
            
            truncated = assembler._manual_truncate(pulse)
            
            # Should truncate
            assert len(truncated["overview"].split()) <= 60
            assert len(truncated["themes"][0]["summary"].split()) <= 20
    
    def test_create_fallback_pulse(self):
        """Test fallback pulse creation"""
        with patch('layer_3_content_generation.pulse_assembler.LLMClient'):
            assembler = PulseAssembler()
            
            fallback = assembler._create_fallback_pulse("2025-12-01", ["Theme 1", "Theme 2", "Theme 3"])
            
            assert fallback["title"] is not None
            assert len(fallback["themes"]) == 3
            assert len(fallback["quotes"]) == 3
            assert len(fallback["actions"]) == 3
    
    def test_pulse_to_text(self):
        """Test converting pulse to text"""
        with patch('layer_3_content_generation.pulse_assembler.LLMClient'):
            assembler = PulseAssembler()
            
            pulse = {
                "title": "Test Title",
                "overview": "Test overview",
                "themes": [{"name": "Theme 1", "summary": "Summary 1"}],
                "quotes": ["Quote 1"],
                "actions": ["Action 1"]
            }
            
            text = assembler._pulse_to_text(pulse)
            
            assert isinstance(text, str)
            assert "Test Title" in text
            assert "Test overview" in text


class TestWeeklyPulseGenerator:
    """Test weekly pulse generator"""
    
    def test_initialization(self):
        """Test generator initialization"""
        generator = WeeklyPulseGenerator()
        assert generator.summarizer is not None
        assert generator.assembler is not None
    
    def test_group_reviews_by_theme(self):
        """Test grouping reviews by theme"""
        generator = WeeklyPulseGenerator()
        
        reviews = [
            {"review_id": "1", "theme": "Theme A", "text": "Review 1"},
            {"review_id": "2", "theme": "Theme A", "text": "Review 2"},
            {"review_id": "3", "theme": "Theme B", "text": "Review 3"},
            {"review_id": "4", "theme": "Theme C", "text": "Review 4"},
        ]
        
        grouped = generator._group_reviews_by_theme(reviews, ["Theme A", "Theme B", "Theme C"])
        
        assert len(grouped["Theme A"]) == 2
        assert len(grouped["Theme B"]) == 1
        assert len(grouped["Theme C"]) == 1
    
    def test_generate_pulse_full_workflow(self):
        """Test full pulse generation workflow"""
        temp_dir = tempfile.mkdtemp()
        temp_pulses_dir = os.path.join(temp_dir, "pulses")
        os.makedirs(temp_pulses_dir, exist_ok=True)
        
        try:
            # Mock settings
            original_data_dir = settings.DATA_DIR
            settings.DATA_DIR = temp_dir
            
            # Create generator with mocked components
            mock_summarizer = Mock()
            mock_summarizer.summarize_theme.return_value = {
                "theme": "Trading Experience",
                "key_points": ["Point 1", "Point 2"],
                "candidate_quotes": ["Quote 1", "Quote 2"]
            }
            
            mock_assembler = Mock()
            mock_assembler.assemble_pulse.return_value = {
                "title": "Test Pulse",
                "overview": "Test overview",
                "themes": [{"name": "Theme 1", "summary": "Summary 1"}],
                "quotes": ["Quote 1"],
                "actions": ["Action 1"]
            }
            mock_assembler._count_words = lambda x: 150
            
            generator = WeeklyPulseGenerator(
                summarizer=mock_summarizer,
                assembler=mock_assembler
            )
            generator.pulses_dir = temp_pulses_dir
            
            # Test data
            theme_data = {
                "week_start_date": "2025-12-01",
                "week_end_date": "2025-12-07",
                "total_reviews": 10,
                "top_themes": [
                    {"theme": "Trading Experience", "count": 5},
                    {"theme": "App Performance", "count": 3},
                    {"theme": "Support", "count": 2}
                ],
                "reviews": [
                    {"review_id": f"r{i}", "theme": "Trading Experience", "text": f"Review {i}"}
                    for i in range(5)
                ] + [
                    {"review_id": f"r{i}", "theme": "App Performance", "text": f"Review {i}"}
                    for i in range(5, 8)
                ] + [
                    {"review_id": f"r{i}", "theme": "Support", "text": f"Review {i}"}
                    for i in range(8, 10)
                ]
            }
            
            result = generator.generate_pulse("2025-12-01", theme_data)
            
            assert result["week_key"] == "2025-12-01"
            assert "pulse" in result
            assert result["pulse"]["title"] == "Test Pulse"
            
            # Verify summarizer was called for each theme
            assert mock_summarizer.summarize_theme.call_count == 3
            
            # Verify assembler was called
            assert mock_assembler.assemble_pulse.call_count == 1
            
            # Verify file was saved
            pulse_file = os.path.join(temp_pulses_dir, "pulse_2025-12-01.json")
            assert os.path.exists(pulse_file)
            
            settings.DATA_DIR = original_data_dir
            
        finally:
            shutil.rmtree(temp_dir)
    
    def test_generate_pulse_no_themes(self):
        """Test pulse generation with no themes"""
        generator = WeeklyPulseGenerator()
        
        theme_data = {
            "week_start_date": "2025-12-01",
            "week_end_date": "2025-12-07",
            "total_reviews": 0,
            "top_themes": [],
            "reviews": []
        }
        
        result = generator.generate_pulse("2025-12-01", theme_data)
        
        assert "error" in result
        assert result["error"] == "No themes available"
    
    def test_save_pulse(self):
        """Test saving pulse to file"""
        temp_dir = tempfile.mkdtemp()
        temp_pulses_dir = os.path.join(temp_dir, "pulses")
        os.makedirs(temp_pulses_dir, exist_ok=True)
        
        try:
            generator = WeeklyPulseGenerator()
            generator.pulses_dir = temp_pulses_dir
            
            pulse_data = {
                "week_key": "2025-12-01",
                "pulse": {
                    "title": "Test Pulse",
                    "overview": "Test",
                    "themes": [],
                    "quotes": [],
                    "actions": []
                }
            }
            
            generator._save_pulse("2025-12-01", pulse_data)
            
            pulse_file = os.path.join(temp_pulses_dir, "pulse_2025-12-01.json")
            assert os.path.exists(pulse_file)
            
            # Verify file contents
            with open(pulse_file, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                assert loaded["week_key"] == "2025-12-01"
                assert loaded["pulse"]["title"] == "Test Pulse"
        
        finally:
            shutil.rmtree(temp_dir)


class TestIntegration:
    """Integration tests for full workflow"""
    
    def test_end_to_end_pulse_generation(self):
        """Test end-to-end pulse generation with mocked LLM"""
        temp_dir = tempfile.mkdtemp()
        temp_pulses_dir = os.path.join(temp_dir, "pulses")
        os.makedirs(temp_pulses_dir, exist_ok=True)
        
        try:
            original_data_dir = settings.DATA_DIR
            settings.DATA_DIR = temp_dir
            
            # Mock LLM client
            mock_llm = Mock()
            
            # Mock summarization response
            mock_llm.generate.side_effect = [
                # Theme summarization responses
                json.dumps({
                    "theme": "Trading Experience",
                    "key_points": ["Point 1", "Point 2"],
                    "candidate_quotes": ["Quote 1", "Quote 2"]
                }),
                # Pulse assembly response
                json.dumps({
                    "title": "Weekly Pulse",
                    "overview": "This week's overview",
                    "themes": [
                        {"name": "Trading Experience", "summary": "Summary 1"}
                    ],
                    "quotes": ["Quote 1"],
                    "actions": ["Action 1"]
                })
            ]
            
            with patch('layer_3_content_generation.theme_summarizer.LLMClient', return_value=mock_llm):
                with patch('layer_3_content_generation.pulse_assembler.LLMClient', return_value=mock_llm):
                    generator = WeeklyPulseGenerator()
                    generator.pulses_dir = temp_pulses_dir
                    
                    theme_data = {
                        "week_start_date": "2025-12-01",
                        "week_end_date": "2025-12-07",
                        "total_reviews": 5,
                        "top_themes": [
                            {"theme": "Trading Experience", "count": 5}
                        ],
                        "reviews": [
                            {"review_id": f"r{i}", "theme": "Trading Experience", "text": f"Review {i} with enough characters" * 2}
                            for i in range(5)
                        ]
                    }
                    
                    result = generator.generate_pulse("2025-12-01", theme_data)
                    
                    assert result["week_key"] == "2025-12-01"
                    assert "pulse" in result
                    assert result["pulse"]["title"] == "Weekly Pulse"
            
            settings.DATA_DIR = original_data_dir
        
        finally:
            shutil.rmtree(temp_dir)


def run_all_tests():
    """Run all test suites"""
    print("=" * 80)
    print("Layer 3 Content Generation - Comprehensive Test Suite")
    print("=" * 80)
    
    test_classes = [
        ("Theme Summarizer", TestThemeSummarizer),
        ("Pulse Assembler", TestPulseAssembler),
        ("Weekly Pulse Generator", TestWeeklyPulseGenerator),
        ("Integration", TestIntegration),
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

