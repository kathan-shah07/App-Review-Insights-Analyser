"""
Storage module for saving reviews as week-level buckets
"""
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict
from collections import defaultdict

from config.settings import settings
from models.review import Review
from layer_1_data_import.validator import ReviewValidator, TextCleaner, PIIDetector, LanguageDetector
from utils.logger import get_logger

logger = get_logger(__name__)


class ReviewStorage:
    """Store reviews as week-level buckets"""
    
    def __init__(self, storage_dir: str = None):
        """
        Initialize storage
        
        Args:
            storage_dir: Directory to store review files
        """
        self.storage_dir = storage_dir or settings.REVIEWS_DIR
        os.makedirs(self.storage_dir, exist_ok=True)
    
    def _get_week_key(self, date: datetime) -> str:
        """
        Get week key for a date (format: YYYY-MM-DD for Monday of that week)
        
        Args:
            date: Review date
        
        Returns:
            Week key string
        """
        # Calculate Monday of the week
        days_since_monday = date.weekday()
        monday = date - timedelta(days=days_since_monday)
        return monday.strftime("%Y-%m-%d")
    
    def _get_filename(self, week_key: str) -> str:
        """Get filename for a week"""
        return os.path.join(self.storage_dir, f"reviews_{week_key}.json")
    
    def save_reviews(self, reviews: List[Review]):
        """
        Save reviews grouped by week
        
        Args:
            reviews: List of Review objects
        """
        # Group reviews by week
        weekly_reviews = defaultdict(list)
        
        for review in reviews:
            week_key = self._get_week_key(review.date)
            weekly_reviews[week_key].append(review.to_dict())
        
        # Save each week's reviews
        for week_key, week_reviews in weekly_reviews.items():
            filename = self._get_filename(week_key)
            
            # Load existing reviews if file exists
            existing_reviews = []
            if os.path.exists(filename):
                try:
                    with open(filename, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                        existing_reviews = existing_data.get('reviews', [])
                except Exception as e:
                    logger.warning(f"Error loading existing reviews from {filename}: {e}")
            
            # Filter existing reviews to ensure they meet quality criteria
            # (non-English, emojis, PII, < 20 chars)
            filtered_existing_reviews = []
            filtered_count = 0
            for r in existing_reviews:
                # Parse date if it's a string
                review_date = r.get('date')
                if isinstance(review_date, str):
                    try:
                        # Try ISO format first (with T separator)
                        if 'T' in review_date:
                            review_date = datetime.fromisoformat(review_date.replace('Z', '+00:00'))
                        else:
                            # Try space-separated format (YYYY-MM-DD HH:MM:SS)
                            try:
                                review_date = datetime.strptime(review_date, "%Y-%m-%d %H:%M:%S")
                            except:
                                # Try date-only format
                                review_date = datetime.strptime(review_date, "%Y-%m-%d")
                    except Exception as e:
                        logger.warning(f"Could not parse date for review {r.get('review_id')}: {review_date} - {e}")
                        continue
                elif not isinstance(review_date, datetime):
                    logger.warning(f"Invalid date type for review {r.get('review_id')}: {type(review_date)}")
                    continue
                
                # Convert to dict format for validation
                review_dict = {
                    'review_id': r.get('review_id'),
                    'title': r.get('title', ''),
                    'text': r.get('text', ''),
                    'date': review_date,
                    'platform': r.get('platform')
                }
                
                # Validate and filter existing review
                processed = ReviewValidator.process_review(review_dict)
                if processed:
                    # Keep only required fields
                    filtered_review = {
                        'review_id': processed.get('review_id'),
                        'text': processed.get('text'),
                        'date': processed.get('date'),
                        'platform': processed.get('platform')
                    }
                    filtered_existing_reviews.append(filtered_review)
                else:
                    filtered_count += 1
            
            # Merge with new reviews (avoid duplicates)
            existing_ids = {r['review_id'] for r in filtered_existing_reviews}
            new_reviews = [r for r in week_reviews if r['review_id'] not in existing_ids]
            
            # Combine filtered existing reviews with new reviews
            all_reviews = filtered_existing_reviews + new_reviews
            
            # Only save if there are reviews (new or filtered existing)
            if all_reviews:
                
                # Save to file
                week_data = {
                    'week_start_date': week_key,
                    'week_end_date': (datetime.strptime(week_key, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d"),
                    'total_reviews': len(all_reviews),
                    'reviews': all_reviews
                }
                
                try:
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(week_data, f, indent=2, ensure_ascii=False, default=str)
                    
                    if filtered_count > 0:
                        logger.info(f"Filtered out {filtered_count} invalid existing reviews from {filename} (kept {len(filtered_existing_reviews)} out of {len(existing_reviews)})")
                    if new_reviews:
                        logger.info(f"Saved {len(new_reviews)} new reviews to {filename} (total: {len(all_reviews)})")
                    elif filtered_count > 0:
                        logger.info(f"Updated {filename} with filtered reviews (total: {len(all_reviews)})")
                except Exception as e:
                    logger.error(f"Error saving reviews to {filename}: {e}")
    
    def load_week_reviews(self, week_key: str) -> List[Dict]:
        """
        Load reviews for a specific week
        
        Args:
            week_key: Week key (YYYY-MM-DD format)
        
        Returns:
            List of review dictionaries
        """
        filename = self._get_filename(week_key)
        
        if not os.path.exists(filename):
            return []
        
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('reviews', [])
        except Exception as e:
            logger.error(f"Error loading reviews from {filename}: {e}")
            return []
    
    def get_available_weeks(self) -> List[str]:
        """Get list of available week keys"""
        weeks = []
        if os.path.exists(self.storage_dir):
            for filename in os.listdir(self.storage_dir):
                if filename.startswith('reviews_') and filename.endswith('.json'):
                    week_key = filename.replace('reviews_', '').replace('.json', '')
                    weeks.append(week_key)
        return sorted(weeks)
    
    def save_raw_reviews(self, raw_reviews: List[Dict], import_timestamp: datetime = None):
        """
        Save raw reviews (before processing) grouped by week
        
        Args:
            raw_reviews: List of raw review dictionaries (before processing)
            import_timestamp: Timestamp when reviews were imported (defaults to now)
        """
        if not raw_reviews:
            logger.info("No raw reviews to save")
            return
        
        # Use raw reviews directory
        raw_storage_dir = settings.RAW_REVIEWS_DIR
        os.makedirs(raw_storage_dir, exist_ok=True)
        
        if import_timestamp is None:
            import_timestamp = datetime.now()
        
        # Group reviews by week
        weekly_reviews = defaultdict(list)
        
        for review in raw_reviews:
            try:
                # Extract date from review
                review_date = review.get('date')
                if isinstance(review_date, str):
                    # Try to parse string date
                    try:
                        review_date = datetime.fromisoformat(review_date.replace('Z', '+00:00'))
                    except:
                        review_date = datetime.now() - timedelta(days=1)
                elif not isinstance(review_date, datetime):
                    review_date = datetime.now() - timedelta(days=1)
                
                week_key = self._get_week_key(review_date)
                weekly_reviews[week_key].append(review)
            except Exception as e:
                logger.warning(f"Error processing raw review for storage: {e}")
                continue
        
        # Save each week's raw reviews
        for week_key, week_reviews in weekly_reviews.items():
            filename = os.path.join(raw_storage_dir, f"raw_reviews_{week_key}.json")
            
            # Load existing raw reviews if file exists
            existing_reviews = []
            if os.path.exists(filename):
                try:
                    with open(filename, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                        existing_reviews = existing_data.get('reviews', [])
                except Exception as e:
                    logger.warning(f"Error loading existing raw reviews from {filename}: {e}")
            
            # Merge with existing reviews (avoid duplicates by review_id)
            existing_ids = {r.get('review_id') for r in existing_reviews if r.get('review_id')}
            new_reviews = [r for r in week_reviews if r.get('review_id') not in existing_ids]
            
            if new_reviews:
                all_reviews = existing_reviews + new_reviews
                
                # Save to file
                week_data = {
                    'week_start_date': week_key,
                    'week_end_date': (datetime.strptime(week_key, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d"),
                    'import_timestamp': import_timestamp.isoformat(),
                    'total_reviews': len(all_reviews),
                    'reviews': all_reviews
                }
                
                try:
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(week_data, f, indent=2, ensure_ascii=False, default=str)
                    logger.info(f"Saved {len(new_reviews)} raw reviews to {filename} (total: {len(all_reviews)})")
                except Exception as e:
                    logger.error(f"Error saving raw reviews to {filename}: {e}")

