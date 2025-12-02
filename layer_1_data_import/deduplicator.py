"""
Deduplication logic to avoid processing same review twice
"""
import json
import os
from typing import List, Dict, Set

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class ReviewDeduplicator:
    """Handle review deduplication using cached review IDs"""
    
    def __init__(self, cache_file: str = None):
        """
        Initialize deduplicator
        
        Args:
            cache_file: Path to cache file storing processed review IDs
        """
        self.cache_file = cache_file or os.path.join(settings.CACHE_DIR, "processed_reviews.json")
        self.processed_ids: Set[str] = self._load_cache()
    
    def _load_cache(self) -> Set[str]:
        """Load processed review IDs from cache file"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return set(data.get('review_ids', []))
            except Exception as e:
                logger.warning(f"Error loading cache file: {e}")
                return set()
        return set()
    
    def _save_cache(self):
        """Save processed review IDs to cache file"""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump({'review_ids': list(self.processed_ids)}, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving cache file: {e}")
    
    def is_duplicate(self, review_id: str) -> bool:
        """
        Check if review ID has been processed before
        
        Args:
            review_id: Review ID to check
        
        Returns:
            True if duplicate, False otherwise
        """
        return review_id in self.processed_ids
    
    def mark_as_processed(self, review_id: str):
        """
        Mark review ID as processed
        
        Args:
            review_id: Review ID to mark
        """
        self.processed_ids.add(review_id)
    
    def filter_duplicates(self, reviews: List[Dict]) -> List[Dict]:
        """
        Filter out duplicate reviews
        
        Args:
            reviews: List of review dictionaries
        
        Returns:
            List of unique reviews
        """
        unique_reviews = []
        duplicates_count = 0
        
        for review in reviews:
            review_id = review.get('review_id')
            if not review_id:
                logger.warning("Review missing review_id, skipping")
                continue
            
            if not self.is_duplicate(review_id):
                unique_reviews.append(review)
                self.mark_as_processed(review_id)
            else:
                duplicates_count += 1
        
        if duplicates_count > 0:
            logger.info(f"Filtered out {duplicates_count} duplicate reviews")
        
        # Save cache after filtering
        self._save_cache()
        
        return unique_reviews
    
    def get_stats(self) -> Dict:
        """Get deduplication statistics"""
        return {
            'total_processed': len(self.processed_ids),
            'cache_file': self.cache_file
        }
