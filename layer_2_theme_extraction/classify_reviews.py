"""
Entry point for classifying reviews into themes

This file takes all the reviews we imported and sorts them into 5 categories (themes).
Think of it like organizing mail into different boxes:
- Feature Requests box
- Bug Reports box
- User Experience Issues box
- Performance Issues box
- Other/General Feedback box

It uses AI (Google's Gemini) to read each review and decide which box it belongs in.
"""
from layer_2_theme_extraction.weekly_processor import WeeklyThemeProcessor
from layer_2_theme_extraction.classifier import REVIEWS_PER_BATCH
from layer_1_data_import.storage import ReviewStorage
from config.settings import settings
from utils.logger import get_logger
from datetime import datetime

logger = get_logger(__name__)


def classify_all_reviews(force_regenerate: bool = False) -> list[dict]:
    """
    Classify all reviews into themes - This is the main function
    
    This function:
    1. Loads all the reviews we imported (organized by week)
    2. For each week, sends reviews to AI in batches of 30
    3. AI reads each review and decides which of 5 themes it belongs to:
       - Feature Requests: Users asking for new features
       - Bug Reports: Users reporting problems or errors
       - User Experience Issues: App is confusing or hard to use
       - Performance Issues: App is slow, crashes, or uses too much battery
       - Other/General Feedback: Everything else
    4. Groups reviews by theme and saves the results
    
    Why batches of 30? Because AI can process multiple reviews at once,
    which is faster and cheaper than doing them one at a time.
    
    Args:
        force_regenerate: If True, regenerate even if themes already exist
    
    Returns:
        List of processing results for each week - shows how many reviews
        were classified and which themes they belong to
    """
    start_time = datetime.now()  # Remember when we started (to calculate how long it takes)
    logger.info("=" * 80)
    logger.info("Starting Theme Classification Workflow")
    logger.info("=" * 80)
    logger.info(f"Batch size: {REVIEWS_PER_BATCH} reviews per prompt")
    logger.info(f"Strategy: Each week's reviews are batched separately")
    if force_regenerate:
        logger.info("Force regenerate: YES - will regenerate all themes")
    else:
        logger.info("Force regenerate: NO - will skip weeks that already have themes")
    # Check if there's a limit on how many reviews to process per week
    # (useful for testing - set to 100 to only process first 100 reviews)
    if settings.MAX_REVIEWS_PER_WEEK > 0:
        logger.info(f"Max reviews per week limit: {settings.MAX_REVIEWS_PER_WEEK}")
    else:
        logger.info("Max reviews per week limit: None (processing all reviews)")
    logger.info("=" * 80)
    
    # Load the reviews we imported earlier
    storage = ReviewStorage()
    available_weeks = storage.get_available_weeks()  # Get list of weeks we have reviews for
    
    if not available_weeks:
        logger.warning("No weeks available for processing")
        return []  # Nothing to do!
    
    # Show the user what we're about to process
    logger.info(f"\nFound {len(available_weeks)} weeks to process:")
    for idx, week in enumerate(available_weeks, 1):
        reviews = storage.load_week_reviews(week)  # Load reviews for this week
        # Count how many are valid (at least 20 characters)
        valid_reviews = [r for r in reviews if len(r.get('text', '').strip()) >= 20]
        logger.info(f"  {idx}. Week {week}: {len(reviews)} total reviews ({len(valid_reviews)} valid >= 20 chars)")
    
    # Create a processor that will do the actual classification
    processor = WeeklyThemeProcessor()
    # Process all weeks - this sends reviews to AI and gets themes back
    results = processor.process_all_weeks(force_regenerate=force_regenerate)
    
    # ============================================================
    # Calculate summary statistics
    # ============================================================
    # Count up how many reviews were successfully classified
    total_classified = sum(r.get('classified_reviews', 0) for r in results if 'classified_reviews' in r)
    total_reviews = sum(r.get('total_reviews', 0) for r in results if 'total_reviews' in r)
    successful_weeks = len([r for r in results if 'error' not in r])  # Weeks that worked
    failed_weeks = len([r for r in results if 'error' in r])  # Weeks that had errors
    skipped_weeks = len([r for r in results if r.get('skipped', False)])  # Weeks that were skipped
    
    # Calculate how many batches we processed (for reporting)
    total_batches = 0
    for result in results:
        if 'classified_reviews' in result:
            classified = result.get('classified_reviews', 0)
            # Calculate batches: if we classified 65 reviews in batches of 30,
            # that's 3 batches (30 + 30 + 5)
            batches = (classified + REVIEWS_PER_BATCH - 1) // REVIEWS_PER_BATCH
            total_batches += batches
    
    # Calculate how long the whole process took
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    # Print a nice summary for the user
    logger.info("\n" + "=" * 80)
    logger.info("Theme Classification Summary")
    logger.info("=" * 80)
    logger.info(f"Processing time: {duration:.2f} seconds ({duration/60:.2f} minutes)")
    logger.info(f"Weeks processed: {successful_weeks}/{len(available_weeks)} successful")
    if skipped_weeks > 0:
        logger.info(f"Skipped (already exist): {skipped_weeks} weeks")
    if failed_weeks > 0:
        logger.warning(f"Failed weeks: {failed_weeks}")
    logger.info(f"Total reviews: {total_reviews}")
    logger.info(f"Classified reviews: {total_classified} ({total_classified/total_reviews*100:.1f}%)" if total_reviews > 0 else "Classified reviews: 0")
    logger.info(f"Total batches processed: {total_batches}")
    logger.info(f"Average reviews per batch: {total_classified/total_batches:.1f}" if total_batches > 0 else "Average reviews per batch: 0")
    
    # Show which themes were most common across all weeks
    # This helps understand what users are talking about most
    all_theme_counts = {}
    for result in results:
        if 'theme_counts' in result:
            for theme, count in result.get('theme_counts', {}).items():
                all_theme_counts[theme] = all_theme_counts.get(theme, 0) + count
    
    if all_theme_counts:
        logger.info(f"\nOverall Theme Distribution:")
        # Sort themes by count (most common first)
        sorted_themes = sorted(all_theme_counts.items(), key=lambda x: x[1], reverse=True)
        for theme, count in sorted_themes:
            percentage = (count / total_classified * 100) if total_classified > 0 else 0
            logger.info(f"  - {theme}: {count} reviews ({percentage:.1f}%)")
    
    logger.info("=" * 80)
    logger.info("Theme classification complete!")
    logger.info("=" * 80)
    
    return results  # Return the results so other parts of the system can use them


def classify_last_week() -> dict:
    """
    Classify only the last week's reviews
    Reviews are batched into groups of 30 and processed with retry logic
    
    Returns:
        Processing result for the last week
    """
    start_time = datetime.now()
    logger.info("=" * 80)
    logger.info("Starting Theme Classification for Last Week Only")
    logger.info("=" * 80)
    logger.info(f"Batch size: {REVIEWS_PER_BATCH} reviews per prompt")
    if settings.MAX_REVIEWS_PER_WEEK > 0:
        logger.info(f"Max reviews per week limit: {settings.MAX_REVIEWS_PER_WEEK}")
    else:
        logger.info("Max reviews per week limit: None (processing all reviews)")
    logger.info("=" * 80)
    
    storage = ReviewStorage()
    available_weeks = storage.get_available_weeks()
    
    if not available_weeks:
        logger.warning("No weeks available for processing")
        return {
            "week_key": None,
            "total_reviews": 0,
            "classified_reviews": 0,
            "theme_counts": {},
            "top_themes": [],
            "error": "No weeks available"
        }
    
    last_week = available_weeks[-1]
    logger.info(f"\nProcessing last week: {last_week}")
    
    # Show review count before processing
    reviews = storage.load_week_reviews(last_week)
    valid_reviews = [r for r in reviews if len(r.get('text', '').strip()) >= 20]
    logger.info(f"Found {len(reviews)} total reviews ({len(valid_reviews)} valid >= 20 chars)")
    
    # Calculate expected batches
    expected_batches = (len(valid_reviews) + REVIEWS_PER_BATCH - 1) // REVIEWS_PER_BATCH
    logger.info(f"Expected batches: {expected_batches} (up to {REVIEWS_PER_BATCH} reviews per batch)")
    
    processor = WeeklyThemeProcessor()
    result = processor.process_week(last_week)
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    # Print detailed results
    logger.info("\n" + "=" * 80)
    logger.info("Classification Results")
    logger.info("=" * 80)
    logger.info(f"Week: {result.get('week_key')}")
    logger.info(f"Processing time: {duration:.2f} seconds ({duration/60:.2f} minutes)")
    logger.info(f"Total reviews: {result.get('total_reviews', 0)}")
    logger.info(f"Classified: {result.get('classified_reviews', 0)}")
    
    if result.get('theme_counts'):
        logger.info(f"\nTheme Distribution:")
        sorted_themes = sorted(result.get('theme_counts', {}).items(), key=lambda x: x[1], reverse=True)
        total = result.get('classified_reviews', 0)
        for theme, count in sorted_themes:
            percentage = (count / total * 100) if total > 0 else 0
            logger.info(f"  - {theme}: {count} reviews ({percentage:.1f}%)")
    
    if result.get('top_themes'):
        top_themes = result.get('top_themes', [])
        if top_themes and isinstance(top_themes[0], tuple):
            logger.info(f"\nTop Themes:")
            for theme, count in top_themes[:5]:
                logger.info(f"  - {theme}: {count} reviews")
    
    logger.info("=" * 80)
    logger.info("Last week classification complete!")
    logger.info("=" * 80)
    
    return result


if __name__ == "__main__":
    # Allow running with --last-week flag
    import sys
    if "--last-week" in sys.argv or "-l" in sys.argv:
        result = classify_last_week()
        print(f"\n✅ Last week classification complete!")
        print(f"Week: {result.get('week_key')}")
        print(f"Total reviews: {result.get('total_reviews', 0)}")
        print(f"Classified: {result.get('classified_reviews', 0)}")
        if result.get('top_themes'):
            top_themes = result.get('top_themes', [])
            # top_themes is a list of tuples (theme, count) or dicts
            if top_themes and isinstance(top_themes[0], tuple):
                themes_str = ', '.join([f"{theme} ({count})" for theme, count in top_themes[:3]])
            else:
                themes_str = ', '.join([f"{t.get('theme')} ({t.get('count')})" for t in top_themes[:3]])
            print(f"Top themes: {themes_str}")
    else:
        results = classify_all_reviews()
        print(f"\n✅ Successfully processed {len(results)} weeks")

