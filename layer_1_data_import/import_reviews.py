"""
Main import workflow: Fetch, validate, deduplicate, and store reviews

This file is responsible for getting reviews from the app stores and preparing them.
Think of it like a quality control process:
- It goes to the stores and downloads reviews
- It checks each review to make sure it's good quality
- It removes duplicates
- It organizes reviews by week (Monday to Sunday)
"""
from datetime import datetime
from typing import List

from config.settings import settings
from models.review import Review
from layer_1_data_import.scraper import fetch_all_reviews
from layer_1_data_import.validator import ReviewValidator, TextCleaner, PIIDetector, LanguageDetector
from layer_1_data_import.deduplicator import ReviewDeduplicator
from layer_1_data_import.storage import ReviewStorage
from utils.logger import get_logger

logger = get_logger(__name__)


def import_reviews() -> List[Review]:
    """
    Main import workflow - This is the main function that does everything
    
    This function works like a factory assembly line:
    1. Fetch reviews from App Store and Play Store
       - Uses a web browser (Playwright) to visit the store pages
       - Downloads all reviews from the past few weeks
    2. Validate and clean reviews
       - Removes reviews that aren't in English
       - Removes reviews with emojis (harder for AI to analyze)
       - Removes reviews with personal info (emails, phone numbers)
       - Removes reviews that are too short (less than 20 characters)
    3. Deduplicate reviews
       - Finds reviews that are exactly the same or very similar
       - Keeps only one copy
    4. Store as week-level buckets
       - Groups reviews by week (Monday to Sunday)
       - Saves them to files so we can use them later
    
    Returns:
        List of imported Review objects - all the reviews that passed quality checks
    """
    logger.info("Starting review import workflow")
    
    # Make sure all the folders we need exist (like creating folders on your computer)
    settings.ensure_directories()
    
    # Figure out what date range to fetch reviews from
    # For example: get reviews from 12 weeks ago to 1 week ago
    start_date, end_date = settings.get_date_range()
    logger.info(f"Importing reviews from {start_date.date()} to {end_date.date()}")
    
    # ============================================================
    # STEP 1: Fetch reviews from the stores
    # ============================================================
    # This opens a web browser, goes to App Store and Play Store,
    # and downloads all the reviews from the date range
    logger.info("Step 1: Fetching reviews from stores...")
    raw_reviews = fetch_all_reviews(start_date, end_date)
    logger.info(f"Fetched {len(raw_reviews)} raw reviews")
    
    # ============================================================
    # STEP 2: Save raw reviews before processing
    # ============================================================
    # Save the original reviews before we clean them up
    # This is like keeping the original photo before editing it
    # Useful if we need to go back and check something
    if raw_reviews:
        logger.info("Step 2: Saving raw reviews...")
        storage = ReviewStorage()
        storage.save_raw_reviews(raw_reviews, datetime.now())
    
    # ============================================================
    # STEP 3: Validate and process reviews
    # ============================================================
    # This is the quality control step. We check each review and
    # only keep the ones that meet our standards:
    # - Must be in English (we can only analyze English reviews)
    # - No emojis (they confuse the AI)
    # - No personal information (emails, phone numbers - privacy!)
    # - Must be at least 20 characters long (too short = not useful)
    logger.info("Step 3: Validating and processing reviews...")
    logger.info("  Filtering criteria:")
    logger.info("    - Non-English reviews will be rejected")
    logger.info("    - Reviews with emojis will be rejected")
    logger.info("    - Reviews with PII will be rejected")
    logger.info("    - Reviews with less than 20 characters (after cleaning) will be rejected")
    
    # These lists will hold our results
    processed_reviews = []  # Reviews that passed all checks
    filtered_stats = {      # Count of reviews we rejected and why
        'emoji': 0,         # How many had emojis
        'pii': 0,           # How many had personal info
        'non_english': 0,   # How many weren't in English
        'too_short': 0,     # How many were too short
        'validation_error': 0  # How many had other problems
    }
    
    # Go through each review one by one and check it
    for raw_review in raw_reviews:
        original_text = raw_review.get('text', '')  # Get the review text
        review_id = raw_review.get('review_id', 'unknown')  # Get the review ID
        
        # Check if review has emojis (like 😀 or ❤️)
        # If it does, skip it and count it in our stats
        if TextCleaner.has_emoji(original_text) or TextCleaner.has_emoji(raw_review.get('title', '')):
            filtered_stats['emoji'] += 1
            continue  # Skip to next review
        
        # Check if review has personal information (PII = Personally Identifiable Information)
        # Like email addresses or phone numbers
        # If it does, skip it for privacy reasons
        if PIIDetector.has_pii(original_text) or PIIDetector.has_pii(raw_review.get('title', '')):
            filtered_stats['pii'] += 1
            continue  # Skip to next review
        
        # Process review (this checks if it's English and long enough)
        # This function cleans the text and validates it
        processed = ReviewValidator.process_review(raw_review)
        if processed:
            # Review passed all checks! Add it to our good reviews list
            processed_reviews.append(processed)
        else:
            # Review failed - figure out why so we can report it
            cleaned_text = TextCleaner.clean(original_text)
            if len(cleaned_text.strip()) < 20:
                filtered_stats['too_short'] += 1  # Too short
            elif not LanguageDetector.is_english(cleaned_text):
                filtered_stats['non_english'] += 1  # Not English
            else:
                filtered_stats['validation_error'] += 1  # Some other problem
    
    # Tell the user how many reviews passed and how many were rejected
    logger.info(f"Processed {len(processed_reviews)} valid reviews")
    if any(filtered_stats.values()):
        logger.info(f"Filtered out:")
        if filtered_stats['emoji'] > 0:
            logger.info(f"  - {filtered_stats['emoji']} reviews with emojis")
        if filtered_stats['pii'] > 0:
            logger.info(f"  - {filtered_stats['pii']} reviews with PII")
        if filtered_stats['non_english'] > 0:
            logger.info(f"  - {filtered_stats['non_english']} non-English reviews")
        if filtered_stats['too_short'] > 0:
            logger.info(f"  - {filtered_stats['too_short']} reviews with less than 20 characters")
        if filtered_stats['validation_error'] > 0:
            logger.info(f"  - {filtered_stats['validation_error']} reviews with validation errors")
    
    # ============================================================
    # STEP 4: Deduplicate
    # ============================================================
    # Sometimes the same review appears multiple times
    # (maybe the user posted it twice, or it's in both stores)
    # We find duplicates and keep only one copy
    logger.info("Step 4: Deduplicating reviews...")
    deduplicator = ReviewDeduplicator()
    unique_reviews = deduplicator.filter_duplicates(processed_reviews)
    logger.info(f"After deduplication: {len(unique_reviews)} unique reviews")
    
    # ============================================================
    # STEP 5: Convert to Review objects
    # ============================================================
    # Convert our review data into Review objects
    # This is like putting the data into a standard format
    # so the rest of the system knows how to use it
    logger.info("Step 5: Converting to Review objects...")
    review_objects = []
    for review_dict in unique_reviews:
        try:
            # Create a Review object with all the review information
            review = Review(
                review_id=review_dict['review_id'],  # Unique ID for this review
                title=review_dict['title'],          # Review title
                text=review_dict['text'],           # Review text (cleaned)
                date=review_dict['date'],            # When the review was written
                platform=review_dict['platform']    # Which store (App Store or Play Store)
            )
            review_objects.append(review)
        except Exception as e:
            # If something goes wrong creating the object, skip it and continue
            logger.warning(f"Error creating Review object: {e}")
            continue
    
    # ============================================================
    # STEP 6: Store reviews
    # ============================================================
    # Save all the reviews to files, organized by week
    # Each week gets its own file (Monday to Sunday)
    # Files are saved in: data/reviews/reviews_YYYY-MM-DD.json
    logger.info("Step 6: Storing reviews...")
    storage.save_reviews(review_objects)
    
    logger.info(f"Import complete! Imported {len(review_objects)} reviews")
    
    return review_objects  # Return the list of reviews we imported


# This part runs when you execute this file directly
# It runs the import process and prints how many reviews were imported
if __name__ == "__main__":
    # Run import
    reviews = import_reviews()
    print(f"\n✅ Successfully imported {len(reviews)} reviews")

