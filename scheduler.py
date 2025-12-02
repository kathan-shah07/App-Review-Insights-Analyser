"""
Scheduler for weekly review import
Runs every Monday at 9 AM IST
"""
import schedule
import time
from datetime import datetime
from layer_1_data_import.import_reviews import import_reviews
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


def run_weekly_import():
    """Run weekly review import"""
    logger.info(f"Scheduled import triggered at {datetime.now()}")
    try:
        reviews = import_reviews()
        logger.info(f"✅ Scheduled import complete! Imported {len(reviews)} reviews")
    except Exception as e:
        logger.error(f"Error in scheduled import: {e}", exc_info=True)


def start_scheduler():
    """Start the scheduler"""
    # Schedule for Monday at 9 AM
    schedule.every().monday.at(f"{settings.SCHEDULE_HOUR:02d}:{settings.SCHEDULE_MINUTE:02d}").do(run_weekly_import)
    
    logger.info(f"Scheduler started. Will run every {settings.SCHEDULE_DAY} at {settings.SCHEDULE_HOUR:02d}:{settings.SCHEDULE_MINUTE:02d}")
    logger.info("Press Ctrl+C to stop")
    
    # Run immediately on start (optional)
    # run_weekly_import()
    
    # Keep running
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute


if __name__ == "__main__":
    try:
        start_scheduler()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")
    except Exception as e:
        logger.error(f"Error in scheduler: {e}", exc_info=True)

