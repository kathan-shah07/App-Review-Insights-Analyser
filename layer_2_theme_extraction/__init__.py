"""
Layer 2: Theme extraction pipeline (LLM-based classification into max 5 themes).
"""
from .theme_config import (
    THEMES,
    get_theme_list,
    get_theme_description,
    is_valid_theme,
    get_fallback_theme,
    get_all_theme_descriptions,
    MIN_REVIEW_LENGTH
)
from .classifier import (
    ReviewClassifier,
    aggregate_theme_counts,
    get_top_themes_by_count
)
from .weekly_processor import WeeklyThemeProcessor
from .classify_reviews import classify_all_reviews

__all__ = [
    'THEMES',
    'get_theme_list',
    'get_theme_description',
    'is_valid_theme',
    'get_fallback_theme',
    'get_all_theme_descriptions',
    'MIN_REVIEW_LENGTH',
    'ReviewClassifier',
    'aggregate_theme_counts',
    'get_top_themes_by_count',
    'WeeklyThemeProcessor',
    'classify_all_reviews',
]

