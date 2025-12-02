"""
Weekly pulse generator - orchestrates the map-reduce workflow
1. Load theme data for a week
2. Filter to top 3 themes
3. Map: Summarize reviews per theme
4. Reduce: Assemble final pulse
"""
import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime

from layer_3_content_generation.theme_summarizer import ThemeSummarizer
from layer_3_content_generation.pulse_assembler import PulseAssembler
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class WeeklyPulseGenerator:
    """Generate weekly pulse for a given week"""
    
    def __init__(self, summarizer: Optional[ThemeSummarizer] = None,
                 assembler: Optional[PulseAssembler] = None):
        """
        Initialize weekly pulse generator
        
        Args:
            summarizer: ThemeSummarizer instance (creates new one if not provided)
            assembler: PulseAssembler instance (creates new one if not provided)
        """
        self.summarizer = summarizer or ThemeSummarizer()
        self.assembler = assembler or PulseAssembler()
        self.pulses_dir = os.path.join(settings.DATA_DIR, "pulses")
        os.makedirs(self.pulses_dir, exist_ok=True)
    
    def generate_pulse(self, week_key: str, theme_data: Dict[str, Any], 
                       force_regenerate: bool = False) -> Dict[str, Any]:
        """
        Generate weekly pulse for a given week
        
        Args:
            week_key: Week key (YYYY-MM-DD)
            theme_data: Theme data dictionary from layer-2 (contains reviews, theme_counts, top_themes)
            force_regenerate: If True, regenerate even if pulse already exists
            
        Returns:
            Dictionary with pulse data and metadata
        """
        # Check if pulse already exists
        pulse_file = os.path.join(self.pulses_dir, f"pulse_{week_key}.json")
        if not force_regenerate and os.path.exists(pulse_file):
            logger.info(f"Pulse already exists for week {week_key}, loading existing...")
            try:
                with open(pulse_file, 'r', encoding='utf-8') as f:
                    existing_pulse = json.load(f)
                logger.info(f"Loaded existing pulse for week {week_key}")
                return existing_pulse
            except Exception as e:
                logger.warning(f"Error loading existing pulse for week {week_key}, will regenerate: {e}")
        
        logger.info(f"Generating weekly pulse for week {week_key}")
        
        # Extract week dates
        week_start = theme_data.get('week_start_date', week_key)
        week_end = theme_data.get('week_end_date', '')
        
        # Get top 3 themes
        top_themes = theme_data.get('top_themes', [])
        
        if not top_themes:
            logger.warning(f"No themes found for week {week_key}")
            return {
                "week_key": week_key,
                "error": "No themes available"
            }
        
        if isinstance(top_themes[0], dict):
            top_3_themes = [
                (t.get('theme'), t.get('count', 0))
                for t in top_themes[:3]
            ]
        else:
            top_3_themes = top_themes[:3]
        
        if not top_3_themes:
            logger.warning(f"No themes found for week {week_key}")
            return {
                "week_key": week_key,
                "error": "No themes available"
            }
        
        logger.info(f"Top 3 themes: {', '.join([f'{t[0]} ({t[1]})' for t in top_3_themes])}")
        
        # Get reviews grouped by theme
        reviews = theme_data.get('reviews', [])
        reviews_by_theme = self._group_reviews_by_theme(reviews, [t[0] for t in top_3_themes])
        
        # Map stage: Summarize each theme
        logger.info("Map stage: Summarizing themes...")
        theme_summaries = []
        
        for theme_name, theme_reviews in reviews_by_theme.items():
            if not theme_reviews:
                continue
            
            logger.info(f"Summarizing theme '{theme_name}' with {len(theme_reviews)} reviews")
            summary = self.summarizer.summarize_theme(theme_name, theme_reviews)
            theme_summaries.append(summary)
        
        # Reduce stage: Assemble final pulse
        logger.info("Reduce stage: Assembling weekly pulse...")
        pulse = self.assembler.assemble_pulse(
            week_key=week_key,
            week_start=week_start,
            week_end=week_end,
            theme_summaries=theme_summaries,
            top_3_themes=top_3_themes
        )
        
        # Add metadata
        pulse_data = {
            "week_key": week_key,
            "week_start_date": week_start,
            "week_end_date": week_end,
            "generated_at": datetime.now().isoformat(),
            "total_reviews": theme_data.get('total_reviews', 0),
            "top_3_themes": [
                {"theme": theme, "count": count}
                for theme, count in top_3_themes
            ],
            "pulse": pulse
        }
        
        # Save pulse
        self._save_pulse(week_key, pulse_data)
        
        # Calculate word count
        word_count = self._count_pulse_words(pulse)
        
        logger.info(f"Weekly pulse generated for week {week_key}")
        logger.info(f"Title: {pulse.get('title', 'N/A')}")
        logger.info(f"Word count: {word_count}")
        
        # Add word count to pulse data
        pulse_data['word_count'] = word_count
        
        return pulse_data
    
    def _group_reviews_by_theme(self, reviews: List[Dict[str, Any]], 
                                theme_names: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group reviews by theme
        
        Args:
            reviews: List of review dictionaries
            theme_names: List of theme names to include
            
        Returns:
            Dictionary mapping theme names to lists of reviews
        """
        reviews_by_theme = {theme: [] for theme in theme_names}
        
        for review in reviews:
            theme = review.get('theme')
            if theme in theme_names:
                reviews_by_theme[theme].append(review)
        
        return reviews_by_theme
    
    def _save_pulse(self, week_key: str, pulse_data: Dict[str, Any]):
        """
        Save pulse to file
        
        Args:
            week_key: Week key
            pulse_data: Pulse data dictionary
        """
        filename = os.path.join(self.pulses_dir, f"pulse_{week_key}.json")
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(pulse_data, f, indent=2, ensure_ascii=False, default=str)
            logger.info(f"Saved pulse to {filename}")
        except Exception as e:
            logger.error(f"Error saving pulse to {filename}: {e}", exc_info=True)
    
    def _count_pulse_words(self, pulse: Dict[str, Any]) -> int:
        """
        Count words in pulse
        
        Args:
            pulse: Pulse dictionary
            
        Returns:
            Word count
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
        return len(full_text.split())

