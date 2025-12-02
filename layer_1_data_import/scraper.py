"""
Scraper for fetching reviews from Play Store
Using google-play-scraper library
"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import time

from google_play_scraper import reviews as play_reviews, Sort

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class PlayStoreScraper:
    """Scraper for Google Play Store reviews using google-play-scraper"""
    
    def __init__(self, app_id: str, app_url: str):
        self.app_id = app_id
        self.app_url = app_url
    
    def fetch_reviews(self, start_date: datetime, end_date: datetime) -> List[Dict]:
        """
        Fetch reviews from Play Store within the specified date range
        
        Args:
            start_date: Start date (inclusive) - only fetch reviews on or after this date
            end_date: End date (inclusive) - only fetch reviews on or before this date
        
        Returns:
            List of review dictionaries within the date range
        """
        reviews = []
        logger.info(f"Fetching Play Store reviews from {start_date.date()} to {end_date.date()}")
        
        try:
            # Fetch reviews using google-play-scraper
            # The library handles pagination automatically
            logger.info(f"Fetching reviews for app: {self.app_id}")
            
            continuation_token = None
            total_fetched = 0
            total_processed = 0
            max_reviews = 2000  # Increased limit to ensure we can fetch reviews across the full date range
            reviews_before_start_date = 0  # Track how many reviews are before start_date
            consecutive_out_of_range = 0  # Track consecutive reviews outside date range
            
            while total_fetched < max_reviews:
                try:
                    # Fetch a batch of reviews
                    result, continuation_token = play_reviews(
                        self.app_id,
                        lang='en',
                        country='in',  # India
                        sort=Sort.NEWEST,  # Sort by newest first
                        count=100,  # Fetch 100 reviews per batch
                        continuation_token=continuation_token
                    )
                    
                    if not result:
                        break
                    
                    batch_in_range = 0
                    batch_out_of_range = 0
                    
                    # Process reviews
                    for review in result:
                        try:
                            total_processed += 1
                            
                            # Parse review date (google-play-scraper returns timestamp in 'at' field)
                            review_date = self._parse_review_date(review.get('at', None))
                            
                            if not review_date:
                                review_date = datetime.now() - timedelta(days=1)
                            
                            # Filter by date range
                            # If review is after end_date, skip it (too new)
                            if review_date > end_date:
                                batch_out_of_range += 1
                                continue
                            
                            # If review is before start_date, we've gone too far back
                            # Stop fetching since we're sorted by NEWEST and won't find older reviews
                            if review_date < start_date:
                                reviews_before_start_date += 1
                                batch_out_of_range += 1
                                consecutive_out_of_range += 1
                                # If we've seen many consecutive reviews before start_date, stop
                                if consecutive_out_of_range >= 50:
                                    logger.info(f"Stopping: Found {consecutive_out_of_range} consecutive reviews before start_date {start_date.date()}")
                                    break
                                continue
                            
                            # Reset consecutive counter if we found a review in range
                            consecutive_out_of_range = 0
                            
                            # Extract review data
                            review_text = review.get('content', '')
                            if not review_text or len(review_text.strip()) < 10:
                                continue
                            
                            user_text = f"{review.get('userName', '')}{review_text}"
                            review_id = f"play_store_{self.app_id}_{abs(hash(user_text))}"
                            
                            reviews.append({
                                "review_id": review_id,
                                "title": review.get('userName', 'User'),  # Use username as title
                                "text": review_text,
                                "date": review_date,
                                "rating": review.get('score', None),
                                "platform": "play_store"
                            })
                            
                            total_fetched += 1
                            batch_in_range += 1
                            
                        except Exception as e:
                            logger.warning(f"Error processing Play Store review: {e}")
                            continue
                    
                    # Log batch statistics
                    if batch_in_range > 0 or batch_out_of_range > 0:
                        logger.debug(f"Batch: {batch_in_range} in range, {batch_out_of_range} out of range")
                    
                    # If we've found many consecutive reviews before start_date, stop fetching
                    if consecutive_out_of_range >= 50:
                        logger.info(f"Stopping fetch: Found {consecutive_out_of_range} consecutive reviews before start_date")
                        break
                    
                    # If no continuation token, we've fetched all reviews
                    if not continuation_token:
                        break
                    
                    # Small delay to avoid rate limiting
                    time.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Error fetching Play Store review batch: {e}")
                    break
            
            logger.info(f"Successfully fetched {len(reviews)} Play Store reviews within date range")
            logger.info(f"Processed {total_processed} total reviews, {reviews_before_start_date} were before start_date")
            
            # Log date range coverage
            if reviews:
                review_dates = [r['date'] for r in reviews]
                min_date = min(review_dates).date()
                max_date = max(review_dates).date()
                logger.info(f"Review date range: {min_date} to {max_date}")
                if min_date > start_date.date():
                    logger.warning(f"Earliest review date ({min_date}) is after start_date ({start_date.date()}) - may be missing older reviews")
                if max_date < end_date.date():
                    logger.warning(f"Latest review date ({max_date}) is before end_date ({end_date.date()}) - may be missing newer reviews")
        
        except Exception as e:
            logger.error(f"Error fetching Play Store reviews: {e}", exc_info=True)
        
        return reviews
    
    def _parse_review_date(self, date_value) -> Optional[datetime]:
        """Parse review date from various formats"""
        if not date_value:
            return None
        
        # If it's already a datetime object
        if isinstance(date_value, datetime):
            return date_value
        
        # If it's a timestamp (common in google-play-scraper)
        if isinstance(date_value, (int, float)):
            try:
                return datetime.fromtimestamp(date_value / 1000)  # Convert from milliseconds
            except:
                try:
                    return datetime.fromtimestamp(date_value)  # Try seconds
                except:
                    pass
        
        # If it's a string, try to parse it
        if isinstance(date_value, str):
            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d",
                "%d %b %Y",
                "%b %d, %Y",
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(date_value.strip(), fmt)
                except:
                    continue
        
        return None


def fetch_all_reviews(start_date: datetime, end_date: datetime) -> List[Dict]:
    """
    Fetch reviews from Play Store
    
    Args:
        start_date: Start date (for logging purposes)
        end_date: End date (for logging purposes)
    
    Returns:
        List of review dictionaries
    """
    # Fetch Play Store reviews
    play_store_scraper = PlayStoreScraper(settings.ANDROID_APP_ID, settings.PLAY_STORE_URL)
    play_store_reviews = play_store_scraper.fetch_reviews(start_date, end_date)
    
    logger.info(f"Total reviews fetched: {len(play_store_reviews)}")
    return play_store_reviews
