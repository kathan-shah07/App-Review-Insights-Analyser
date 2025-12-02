"""
Weekly theme processor - processes reviews week-by-week and assigns themes
"""
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

from layer_1_data_import.storage import ReviewStorage
from layer_2_theme_extraction.classifier import ReviewClassifier, aggregate_theme_counts, get_top_themes_by_count
from layer_2_theme_extraction.theme_config import MIN_REVIEW_LENGTH
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class WeeklyThemeProcessor:
    """Process reviews week-by-week and assign themes"""
    
    def __init__(self, storage: Optional[ReviewStorage] = None, classifier: Optional[ReviewClassifier] = None):
        """
        Initialize weekly processor
        
        Args:
            storage: ReviewStorage instance (creates new one if not provided)
            classifier: ReviewClassifier instance (creates new one if not provided)
        """
        self.storage = storage or ReviewStorage()
        self.classifier = classifier or ReviewClassifier()
        self.themes_dir = settings.THEMES_DIR
        os.makedirs(self.themes_dir, exist_ok=True)
    
    def process_week(self, week_key: str, force_regenerate: bool = False) -> Dict[str, Any]:
        """
        Process reviews for a specific week
        
        Args:
            week_key: Week key (YYYY-MM-DD format)
            force_regenerate: If True, regenerate even if themes already exist
            
        Returns:
            Dictionary with processing results
        """
        # Check if themes already exist
        themes_file = os.path.join(self.themes_dir, f"themes_{week_key}.json")
        if not force_regenerate and os.path.exists(themes_file):
            logger.info(f"Themes already exist for week {week_key}, skipping regeneration...")
            try:
                with open(themes_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                logger.info(f"Loaded existing themes for week {week_key}")
                return {
                    "week_key": week_key,
                    "total_reviews": existing_data.get("total_reviews", 0),
                    "classified_reviews": existing_data.get("total_reviews", 0),
                    "theme_counts": existing_data.get("theme_counts", {}),
                    "top_themes": existing_data.get("top_themes", []),
                    "skipped": True,
                    "message": "Themes already exist, skipped regeneration"
                }
            except Exception as e:
                logger.warning(f"Error loading existing themes for week {week_key}, will regenerate: {e}")
        
        logger.info(f"Processing themes for week {week_key}")
        
        # Load reviews for the week
        reviews = self.storage.load_week_reviews(week_key)
        
        if not reviews:
            logger.info(f"No reviews found for week {week_key}")
            return {
                "week_key": week_key,
                "total_reviews": 0,
                "classified_reviews": 0,
                "theme_counts": {},
                "top_themes": []
            }
        
        # Filter out short reviews
        valid_reviews = [
            review for review in reviews
            if len(review.get('text', '').strip()) >= MIN_REVIEW_LENGTH
        ]
        
        logger.info(f"Found {len(reviews)} reviews, {len(valid_reviews)} valid (>= {MIN_REVIEW_LENGTH} chars)")
        
        if not valid_reviews:
            logger.info(f"No valid reviews for week {week_key}")
            return {
                "week_key": week_key,
                "total_reviews": len(reviews),
                "classified_reviews": 0,
                "theme_counts": {},
                "top_themes": []
            }
        
        # Apply max reviews per week limit if configured
        max_reviews = settings.MAX_REVIEWS_PER_WEEK
        reviews_to_process = valid_reviews
        if max_reviews > 0 and len(valid_reviews) > max_reviews:
            reviews_to_process = valid_reviews[:max_reviews]
            logger.info(f"Limiting to {max_reviews} reviews per week (found {len(valid_reviews)}, processing first {max_reviews})")
        elif max_reviews > 0:
            logger.info(f"Max reviews per week limit: {max_reviews} (found {len(valid_reviews)} reviews)")
        
        # Classify reviews
        classifications = self.classifier.classify_batch(reviews_to_process, batch_name=f"week_{week_key}")
        
        # Aggregate theme counts
        theme_counts = aggregate_theme_counts(classifications)
        top_themes = get_top_themes_by_count(classifications, max_themes=5)
        
        # Enrich reviews with theme assignments
        enriched_reviews = self._enrich_reviews_with_themes(reviews, classifications)
        
        # Save theme assignments
        self._save_theme_assignments(week_key, enriched_reviews, theme_counts, top_themes)
        
        logger.info(f"Week {week_key}: Classified {len(classifications)} reviews into {len(theme_counts)} themes")
        logger.info(f"Top themes: {', '.join([f'{theme} ({count})' for theme, count in top_themes[:3]])}")
        
        return {
            "week_key": week_key,
            "total_reviews": len(reviews),
            "classified_reviews": len(classifications),
            "theme_counts": theme_counts,
            "top_themes": top_themes
        }
    
    def _enrich_reviews_with_themes(self, reviews: List[Dict[str, Any]], classifications: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enrich reviews with theme assignments
        
        Args:
            reviews: Original review list
            classifications: Classification results
            
        Returns:
            Enriched reviews with theme information
        """
        classification_map = {
            c.get('review_id'): c
            for c in classifications
        }
        
        enriched = []
        for review in reviews:
            review_id = review.get('review_id')
            classification = classification_map.get(review_id)
            
            enriched_review = review.copy()
            if classification:
                enriched_review['theme'] = classification.get('chosen_theme')
                enriched_review['theme_reason'] = classification.get('short_reason')
            else:
                # Review was too short or not classified
                enriched_review['theme'] = None
                enriched_review['theme_reason'] = None
            
            enriched.append(enriched_review)
        
        return enriched
    
    def _save_theme_assignments(self, week_key: str, enriched_reviews: List[Dict[str, Any]], 
                                 theme_counts: Dict[str, int], top_themes: List[tuple[str, int]]):
        """
        Save theme assignments to file
        
        Args:
            week_key: Week key
            enriched_reviews: Reviews with theme assignments
            theme_counts: Theme count dictionary
            top_themes: Top themes list
        """
        filename = os.path.join(self.themes_dir, f"themes_{week_key}.json")
        
        from datetime import timedelta
        week_start = datetime.strptime(week_key, "%Y-%m-%d")
        week_end = week_start + timedelta(days=6)
        
        week_data = {
            "week_key": week_key,
            "week_start_date": week_key,
            "week_end_date": week_end.strftime("%Y-%m-%d"),
            "total_reviews": len(enriched_reviews),
            "theme_counts": theme_counts,
            "top_themes": [
                {"theme": theme, "count": count}
                for theme, count in top_themes
            ],
            "reviews": enriched_reviews
        }
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(week_data, f, indent=2, ensure_ascii=False, default=str)
            logger.info(f"Saved theme assignments to {filename}")
        except Exception as e:
            logger.error(f"Error saving theme assignments to {filename}: {e}", exc_info=True)
    
    def process_all_weeks(self, force_regenerate: bool = False) -> List[Dict[str, Any]]:
        """
        Process all available weeks - each week's reviews are batched and sent in separate prompts
        
        This strategy:
        - Processes each week independently
        - Batches all reviews from a week into a single prompt
        - Processes weeks sequentially
        
        Args:
            force_regenerate: If True, regenerate even if themes already exist
        
        Returns:
            List of processing results for each week
        """
        available_weeks = self.storage.get_available_weeks()
        
        if not available_weeks:
            logger.info("No weeks available for processing")
            return []
        
        if force_regenerate:
            logger.info(f"Force regenerate enabled - will regenerate all themes")
        else:
            logger.info(f"Will skip weeks that already have themes (use force_regenerate=True to override)")
        
        logger.info(f"Processing {len(available_weeks)} weeks (each week batched in separate prompts)")
        
        results = []
        skipped_count = 0
        for week_key in available_weeks:
            try:
                logger.info(f"\n{'='*60}")
                logger.info(f"Processing week {week_key}")
                logger.info(f"{'='*60}")
                
                # Process each week independently - each week gets its own prompt
                result = self.process_week(week_key, force_regenerate=force_regenerate)
                results.append(result)
                
                if result.get("skipped"):
                    skipped_count += 1
                
            except Exception as e:
                logger.error(f"Error processing week {week_key}: {e}", exc_info=True)
                results.append({
                    "week_key": week_key,
                    "error": str(e)
                })
        
        successful = len([r for r in results if 'error' not in r])
        total_reviews = sum(r.get('total_reviews', 0) for r in results if 'total_reviews' in r)
        total_classified = sum(r.get('classified_reviews', 0) for r in results if 'classified_reviews' in r)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing complete: {successful}/{len(available_weeks)} weeks successful")
        if skipped_count > 0:
            logger.info(f"Skipped (already exist): {skipped_count} weeks")
        logger.info(f"Total reviews: {total_reviews}, Classified: {total_classified}")
        logger.info(f"{'='*60}")
        
        return results

