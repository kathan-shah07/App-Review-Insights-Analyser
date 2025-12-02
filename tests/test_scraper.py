"""
Test script for layer_1_data_import scraper
"""
import sys
from datetime import datetime, timedelta
from layer_1_data_import.scraper import PlayStoreScraper, fetch_all_reviews
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


def test_play_store_scraper():
    """Test Play Store scraper"""
    print("\n" + "=" * 60)
    print("Testing Play Store Scraper")
    print("=" * 60)
    
    # Use a shorter date range for testing (last 30 days)
    end_date = datetime.now() - timedelta(days=7)
    start_date = datetime.now() - timedelta(days=30)
    
    print(f"Date range: {start_date.date()} to {end_date.date()}")
    print(f"Play Store URL: {settings.PLAY_STORE_URL}")
    print(f"App ID: {settings.ANDROID_APP_ID}")
    print("\nFetching reviews... (this may take a minute)")
    
    try:
        scraper = PlayStoreScraper(settings.ANDROID_APP_ID, settings.PLAY_STORE_URL)
        reviews = scraper.fetch_reviews(start_date, end_date)
        
        print(f"\n✅ Successfully fetched {len(reviews)} Play Store reviews")
        
        if reviews:
            print("\nSample reviews:")
            for i, review in enumerate(reviews[:3], 1):
                print(f"\n--- Review {i} ---")
                print(f"ID: {review.get('review_id', 'N/A')}")
                print(f"Title: {review.get('title', 'N/A')[:50]}...")
                print(f"Text: {review.get('text', 'N/A')[:100]}...")
                print(f"Date: {review.get('date', 'N/A')}")
                print(f"Rating: {review.get('rating', 'N/A')}")
                print(f"Platform: {review.get('platform', 'N/A')}")
        
        return reviews
    
    except Exception as e:
        print(f"\n❌ Error testing Play Store scraper: {e}")
        logger.error(f"Play Store scraper test failed: {e}", exc_info=True)
        return []


def test_fetch_all_reviews():
    """Test fetching reviews from Play Store"""
    print("\n" + "=" * 60)
    print("Testing fetch_all_reviews() - Play Store")
    print("=" * 60)
    
    # Use a shorter date range for testing
    end_date = datetime.now() - timedelta(days=7)
    start_date = datetime.now() - timedelta(days=30)
    
    print(f"Date range: {start_date.date()} to {end_date.date()}")
    print("\nFetching reviews from Play Store... (this may take a minute)")
    
    try:
        reviews = fetch_all_reviews(start_date, end_date)
        
        print(f"\n✅ Successfully fetched {len(reviews)} total reviews")
        
        # Count by platform
        play_store_count = sum(1 for r in reviews if r.get('platform') == 'play_store')
        
        print(f"  - Play Store: {play_store_count} reviews")
        
        if reviews:
            print("\nSample reviews:")
            for i, review in enumerate(reviews[:5], 1):
                print(f"\n--- Review {i} ({review.get('platform', 'unknown')}) ---")
                print(f"ID: {review.get('review_id', 'N/A')}")
                print(f"Title: {review.get('title', 'N/A')[:50]}...")
                print(f"Text: {review.get('text', 'N/A')[:100]}...")
                print(f"Date: {review.get('date', 'N/A')}")
                print(f"Rating: {review.get('rating', 'N/A')}")
        
        return reviews
    
    except Exception as e:
        print(f"\n❌ Error testing fetch_all_reviews: {e}")
        logger.error(f"fetch_all_reviews test failed: {e}", exc_info=True)
        return []


def main():
    """Run all scraper tests"""
    print("=" * 60)
    print("Layer 1 Data Import - Scraper Test Suite")
    print("=" * 60)
    
    # Ensure directories exist
    settings.ensure_directories()
    
    # Ask user which test to run
    print("\nSelect test to run:")
    print("1. Test Play Store scraper only")
    print("2. Test fetch_all_reviews (Play Store)")
    
    choice = input("\nEnter choice (1-2) [default: 2]: ").strip() or "2"
    
    results = {
        'play_store': [],
        'all': []
    }
    
    try:
        if choice == "1":
            results['play_store'] = test_play_store_scraper()
        
        elif choice == "2":
            results['all'] = test_fetch_all_reviews()
        
        else:
            print(f"\n❌ Invalid choice: {choice}")
            return 1
        
        # Summary
        print("\n" + "=" * 60)
        print("Test Summary")
        print("=" * 60)
        print(f"Play Store reviews: {len(results['play_store'])}")
        print(f"Total reviews (fetch_all): {len(results['all'])}")
        
        total_reviews = len(results['play_store']) + len(results['all'])
        
        if total_reviews > 0:
            print(f"\n✅ Tests completed successfully! Total reviews fetched: {total_reviews}")
        else:
            print(f"\n⚠️  No reviews were fetched. This could be normal if:")
            print("   - No reviews exist in the date range")
            print("   - The app URLs have changed")
            print("   - There are network/scraping issues")
            print("\nCheck the logs for more details: logs/app.log")
        
        return 0
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        logger.error(f"Test suite failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

