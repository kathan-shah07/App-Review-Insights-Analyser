"""
Application settings and configuration

This file contains all the settings for the application.
Think of it like a control panel where you can adjust how the system works.

Most settings can be changed by creating a .env file in the project root.
If a setting isn't in .env, it uses the default value shown here.
"""
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables from .env file (if it exists)
# This lets you configure the app without changing code
load_dotenv()


class Settings:
    """
    Application configuration settings
    
    This class holds all the configuration for the entire application.
    You can change these values by setting environment variables in a .env file.
    """
    
    # ============================================================
    # App Store URLs
    # ============================================================
    # These are the web addresses where the app is listed
    # The system uses these to find and download reviews
    APP_STORE_URL = os.getenv(
        "APP_STORE_URL",
        "https://apps.apple.com/in/app/groww-stocks-mutual-fund-ipo/id1404871703"
    )
    PLAY_STORE_URL = os.getenv(
        "PLAY_STORE_URL",
        "https://play.google.com/store/apps/details?id=com.nextbillion.groww&hl=en_IN"
    )
    
    # ============================================================
    # App IDs
    # ============================================================
    # Unique identifiers for the app in each store
    # Used to find the right app when scraping reviews
    ANDROID_APP_ID = os.getenv("ANDROID_APP_ID", "com.nextbillion.groww")
    APPLE_APP_ID = os.getenv("APPLE_APP_ID", "1404871703")
    
    # ============================================================
    # Review Import Settings
    # ============================================================
    # How far back to look for reviews
    # Default: Get reviews from the past 12 weeks (but not the last 7 days)
    # Why exclude last 7 days? Because reviews from today might not be complete yet
    WEEKS_TO_FETCH = int(os.getenv("WEEKS_TO_FETCH", "12"))  # 8-12 weeks
    LOOKBACK_DAYS = WEEKS_TO_FETCH * 7  # Convert weeks to days (12 weeks = 84 days)
    DAYS_BACK_START = int(os.getenv("DAYS_BACK_START", "84"))  # Start from 12 weeks ago
    DAYS_BACK_END = int(os.getenv("DAYS_BACK_END", "7"))  # Stop 7 days ago (exclude recent)
    
    # ============================================================
    # Storage Settings
    # ============================================================
    # Where to save all the data files
    # All data is stored in JSON files organized by week
    DATA_DIR = os.getenv("DATA_DIR", "data")  # Main data folder
    REVIEWS_DIR = os.path.join(DATA_DIR, "reviews")  # Where processed reviews go
    RAW_REVIEWS_DIR = os.path.join(DATA_DIR, "reviews", "raw")  # Original reviews before cleaning
    THEMES_DIR = os.path.join(DATA_DIR, "themes")  # Reviews organized by theme
    PULSES_DIR = os.path.join(DATA_DIR, "pulses")  # Weekly summary reports
    EMAILS_DIR = os.path.join(DATA_DIR, "emails")  # Email templates
    CACHE_DIR = os.path.join(DATA_DIR, "cache")  # Temporary cache files
    CHROMA_DB_DIR = os.getenv("CHROMA_DB_DIR", os.path.join(CACHE_DIR, "chroma"))  # Vector database for similarity search
    
    # ============================================================
    # Gemini API Settings
    # ============================================================
    # Google's Gemini AI is used to:
    # - Classify reviews into themes
    # - Generate summaries
    # - Write emails
    # You need an API key from Google to use this
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")  # Your Google API key (required!)
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")  # Which AI model to use
    # Options: gemini-1.5-flash (fast, cheap), gemini-1.5-pro (slower, smarter)
    GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-001")  # For similarity search
    
    # ============================================================
    # LLM Batching & Rate Limiting
    # ============================================================
    # These settings control how we send requests to the AI
    # Batching = sending multiple reviews at once (faster, cheaper)
    # Rate limiting = waiting between requests (to avoid hitting API limits)
    LLM_BATCH_SIZE = int(os.getenv("LLM_BATCH_SIZE", "100"))  # How many reviews to send at once
    LLM_MAX_TOKENS_PER_BATCH = int(os.getenv("LLM_MAX_TOKENS_PER_BATCH", "800000"))  # Max text per batch
    LLM_EMBEDDING_BATCH_SIZE = int(os.getenv("LLM_EMBEDDING_BATCH_SIZE", "100"))  # Batch size for embeddings
    LLM_RETRY_ATTEMPTS = int(os.getenv("LLM_RETRY_ATTEMPTS", "5"))  # How many times to retry if it fails
    LLM_RETRY_DELAY_BASE = float(os.getenv("LLM_RETRY_DELAY_BASE", "2.0"))  # Wait 2 seconds between retries
    LLM_BATCH_DELAY = float(os.getenv("LLM_BATCH_DELAY", "2.0"))  # Wait 2 seconds between batches
    LLM_RATE_LIMIT_DELAY = float(os.getenv("LLM_RATE_LIMIT_DELAY", "15.0"))  # Wait 15 seconds if rate limited
    
    # ============================================================
    # Clustering Settings
    # ============================================================
    # These control how reviews are grouped together
    # (Currently not heavily used, but available for future features)
    HDBSCAN_MIN_CLUSTER_SIZE = int(os.getenv("HDBSCAN_MIN_CLUSTER_SIZE", "5"))  # Min reviews to form a group
    HDBSCAN_MIN_SAMPLES = int(os.getenv("HDBSCAN_MIN_SAMPLES", "2"))  # Min samples for clustering
    MAX_THEME_CLUSTERS = int(os.getenv("MAX_THEME_CLUSTERS", "5"))  # Max number of theme groups
    
    # ============================================================
    # Layer-2 Review Processing Limit
    # ============================================================
    # For testing: limit how many reviews to process per week
    # Set to 0 for no limit (process all reviews)
    # Set to 100 to only process first 100 reviews (useful for testing)
    MAX_REVIEWS_PER_WEEK = int(os.getenv("MAX_REVIEWS_PER_WEEK", "0"))  # 0 = no limit
    
    # ============================================================
    # Scheduler Settings (for cron)
    # ============================================================
    # When to automatically run the import process
    # Default: Every Monday at 9:00 AM
    SCHEDULE_DAY = os.getenv("SCHEDULE_DAY", "monday")  # Day of week (monday, tuesday, etc.)
    SCHEDULE_HOUR = int(os.getenv("SCHEDULE_HOUR", "9"))  # Hour (24-hour format, 9 = 9 AM)
    SCHEDULE_MINUTE = int(os.getenv("SCHEDULE_MINUTE", "0"))  # Minute (0 = on the hour)
    
    # ============================================================
    # Logging Settings
    # ============================================================
    # How much detail to log
    # Options: DEBUG (very detailed), INFO (normal), WARNING (only problems), ERROR (only errors)
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "logs/app.log")  # Where to save log files
    
    # ============================================================
    # Email Settings
    # ============================================================
    # Configuration for sending emails
    # For Gmail: You need to create an "App Password" (not your regular password)
    # See README for instructions on setting up Gmail
    PRODUCT_NAME = os.getenv("PRODUCT_NAME", "Groww")  # Name of your product (appears in emails)
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")  # Email server (Gmail by default)
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))  # Port number (587 for Gmail with TLS)
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")  # Your email address
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")  # Your App Password (for Gmail)
    FROM_EMAIL = os.getenv("FROM_EMAIL", "")  # Email address to send from
    TO_EMAIL = os.getenv("TO_EMAIL", "")  # Email address to send to
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"  # Use encryption (required for Gmail)
    
    @staticmethod
    def get_date_range():
        """
        Get the date range for review import
        
        This calculates what date range to fetch reviews from.
        Example: If today is Dec 1, and DAYS_BACK_START=84, DAYS_BACK_END=7:
        - Start date: Dec 1 - 84 days = Sep 8
        - End date: Dec 1 - 7 days = Nov 24
        So we'd fetch reviews from Sep 8 to Nov 24
        
        Returns:
            Tuple of (start_date, end_date) - the date range to fetch reviews from
        """
        today = datetime.now()
        end_date = today - timedelta(days=Settings.DAYS_BACK_END)  # Go back this many days
        start_date = today - timedelta(days=Settings.DAYS_BACK_START)  # Start from this many days ago
        return start_date, end_date
    
    @staticmethod
    def ensure_directories():
        """
        Create necessary directories if they don't exist
        
        This makes sure all the folders we need exist.
        Like creating folders on your computer - if they don't exist, create them.
        This prevents errors when trying to save files.
        """
        import os
        # Create all the folders we need for storing data
        os.makedirs(Settings.DATA_DIR, exist_ok=True)  # Main data folder
        os.makedirs(Settings.REVIEWS_DIR, exist_ok=True)  # Processed reviews
        os.makedirs(Settings.RAW_REVIEWS_DIR, exist_ok=True)  # Raw reviews
        os.makedirs(Settings.THEMES_DIR, exist_ok=True)  # Theme files
        os.makedirs(Settings.PULSES_DIR, exist_ok=True)  # Pulse files
        os.makedirs(Settings.EMAILS_DIR, exist_ok=True)  # Email templates
        os.makedirs(Settings.CACHE_DIR, exist_ok=True)  # Cache
        os.makedirs(Settings.CHROMA_DB_DIR, exist_ok=True)  # Vector database
        # Create logs folder (extract folder name from log file path)
        os.makedirs(os.path.dirname(Settings.LOG_FILE) if os.path.dirname(Settings.LOG_FILE) else "logs", exist_ok=True)


# Global settings instance
settings = Settings()
