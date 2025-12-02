"""
Main entry point for the application

This is the main file that runs the entire pipeline. Think of it as the "conductor" 
that orchestrates all 4 steps of the process:
1. Get reviews from app stores
2. Organize reviews into themes
3. Create summary reports
4. Send email updates

When you run this file, it automatically goes through all 4 steps in order.
"""
import sys
# Import the functions we need from each layer
from layer_1_data_import.import_reviews import import_reviews
from layer_2_theme_extraction.classify_reviews import classify_all_reviews
from utils.logger import get_logger

# Set up logging so we can see what's happening
logger = get_logger(__name__)


def main():
    """
    Main entry point - This function runs the complete workflow
    
    This function is like a recipe that follows these steps:
    1. Get reviews from App Store and Play Store
    2. Sort reviews into 5 categories (themes)
    3. Create a one-page summary for each week
    4. Write and send an email with the summary
    
    If anything goes wrong, it will log the error and stop gracefully.
    """
    try:
        # Print a nice header to show we're starting
        logger.info("=" * 60)
        logger.info("App Review Insights Analyser - Starting")
        logger.info("=" * 60)
        
        # ============================================================
        # STEP 1: Import Reviews
        # ============================================================
        # This step goes to the App Store and Play Store websites,
        # downloads all the reviews from the past few weeks,
        # cleans them up (removes duplicates, filters bad ones),
        # and saves them organized by week
        logger.info("\n" + "=" * 60)
        logger.info("STEP 1: Importing Reviews")
        logger.info("=" * 60)
        
        reviews = import_reviews()  # This does all the work above
        
        logger.info("\n" + "=" * 60)
        logger.info(f"✅ Review import complete! Imported {len(reviews)} reviews")
        logger.info("=" * 60)
        
        # ============================================================
        # STEP 2: Group into Max 5 Themes
        # ============================================================
        # This step takes all the reviews and sorts them into 5 categories:
        # - Feature Requests (users asking for new features)
        # - Bug Reports (users reporting problems)
        # - User Experience Issues (confusing or hard to use)
        # - Performance Issues (app is slow or crashes)
        # - Other/General Feedback (everything else)
        # 
        # It uses AI (Google's Gemini) to read each review and decide 
        # which category it belongs to
        logger.info("\n" + "=" * 60)
        logger.info("STEP 2: Group into Max 5 Themes")
        logger.info("=" * 60)
        
        theme_results = classify_all_reviews()  # AI sorts reviews into themes
        
        logger.info("\n" + "=" * 60)
        logger.info(f"✅ Theme classification complete! Processed {len(theme_results)} weeks")
        logger.info("=" * 60)
        
        # ============================================================
        # STEP 3: Generate Weekly One-Page Notes
        # ============================================================
        # This step creates a short summary (250 words or less) for each week
        # that includes:
        # - A title summarizing the week
        # - Top 3 themes (most common issues)
        # - 3 representative quotes from users
        # - 3 action items (things the team should do)
        # 
        # It uses AI to write this summary in a clear, concise way
        logger.info("\n" + "=" * 60)
        logger.info("STEP 3: Generate Weekly One-Page Notes")
        logger.info("=" * 60)
        
        from layer_3_content_generation.generate_pulse import generate_all_pulses
        
        pulse_results = generate_all_pulses()  # AI creates the summaries
        
        # Count how many were successful (no errors)
        successful_pulses = len([r for r in pulse_results if 'error' not in r])
        logger.info("\n" + "=" * 60)
        logger.info(f"✅ Pulse generation complete! Generated {successful_pulses} pulses")
        logger.info("=" * 60)
        
        # ============================================================
        # STEP 4: Draft and Send Weekly Email
        # ============================================================
        # This step takes the weekly summary and turns it into an email
        # that can be sent to the team. It:
        # - Writes a nice email body (350 words or less)
        # - Checks for any personal information (emails, phone numbers) and removes it
        # - Creates a subject line
        # - Optionally sends the email (default is preview mode - safe!)
        logger.info("\n" + "=" * 60)
        logger.info("STEP 4: Draft and Send Weekly Email")
        logger.info("=" * 60)
        
        from layer_4_distribution.generate_email import generate_and_send_all_emails
        
        # Generate email previews (not sending by default for safety)
        # This means it creates the email but doesn't send it
        # To actually send, you need to add --send flag when running
        email_results = generate_and_send_all_emails(send=False)
        
        successful_emails = len([r for r in email_results if r.get('success')])
        logger.info("\n" + "=" * 60)
        logger.info(f"✅ Email generation complete! Generated {successful_emails} email previews")
        logger.info("Note: Emails are in preview mode. Use --send flag to actually send.")
        logger.info("=" * 60)
        
        return 0  # Return 0 means "success"
    
    except Exception as e:
        # If something goes wrong, log the error and return 1 (error code)
        logger.error(f"Error in main workflow: {e}", exc_info=True)
        return 1


# This part runs when you execute this file directly (not when imported)
# It calls the main() function and exits with the return code (0 = success, 1 = error)
if __name__ == "__main__":
    sys.exit(main())
