"""
Entry point for generating weekly pulses

This file creates the weekly summary reports (called "pulses").
A pulse is a one-page summary (250 words or less) that includes:
- A title summarizing the week
- An overview paragraph
- Top 3 themes (most common issues)
- 3 representative quotes from users
- 3 action items (things the team should do)

Think of it like a weekly newsletter that tells the team what users are saying.
"""
import json
import os
from typing import List, Dict, Any

from layer_3_content_generation.weekly_pulse_generator import WeeklyPulseGenerator
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


def generate_all_pulses() -> List[Dict[str, Any]]:
    """
    Generate pulses for all available weeks - Main function
    
    This function:
    1. Finds all the theme files we created in Layer 2
    2. For each week, uses AI to create a summary
    3. The summary includes:
       - Title: One line that captures the week
       - Overview: 2-3 sentences explaining what happened
       - Top 3 Themes: The most common issues users mentioned
       - 3 Quotes: Real quotes from users that represent the themes
       - 3 Action Items: Specific things the team should do
    
    Returns:
        List of pulse data dictionaries - one for each week
    """
    logger.info("=" * 80)
    logger.info("Starting Weekly Pulse Generation Workflow")
    logger.info("=" * 80)
    
    # Find where we stored the theme files
    themes_dir = settings.THEMES_DIR
    if not os.path.exists(themes_dir):
        logger.error(f"Themes directory not found: {themes_dir}")
        return []  # Can't continue without theme files
    
    # Find all theme files (they're named like: themes_2025-11-24.json)
    theme_files = [
        f for f in os.listdir(themes_dir)
        if f.startswith('themes_') and f.endswith('.json')
    ]
    
    if not theme_files:
        logger.warning("No theme files found")
        return []  # Nothing to process
    
    logger.info(f"Found {len(theme_files)} weeks to process")
    
    # Create a generator that will create the pulses
    generator = WeeklyPulseGenerator()
    results = []  # Will hold all the pulses we create
    
    # Process each week one by one
    for theme_file in sorted(theme_files):
        # Extract the week date from filename (themes_2025-11-24.json -> 2025-11-24)
        week_key = theme_file.replace('themes_', '').replace('.json', '')
        
        try:
            logger.info(f"\n{'=' * 80}")
            logger.info(f"Processing week: {week_key}")
            logger.info(f"{'=' * 80}")
            
            # Load the theme data for this week
            # This contains all the reviews organized by theme
            theme_file_path = os.path.join(themes_dir, theme_file)
            with open(theme_file_path, 'r', encoding='utf-8') as f:
                theme_data = json.load(f)
            
            # Generate the pulse (summary) for this week
            # This uses AI to read all the themes and create a concise summary
            pulse_data = generator.generate_pulse(week_key, theme_data)
            results.append(pulse_data)
            
        except Exception as e:
            # If something goes wrong, log the error but continue with other weeks
            logger.error(f"Error generating pulse for week {week_key}: {e}", exc_info=True)
            results.append({
                "week_key": week_key,
                "error": str(e)
            })
    
    # Count how many were successful
    successful = len([r for r in results if 'error' not in r])
    logger.info(f"\n{'=' * 80}")
    logger.info(f"Pulse Generation Summary")
    logger.info(f"{'=' * 80}")
    logger.info(f"Processed: {successful}/{len(theme_files)} weeks successfully")
    logger.info(f"{'=' * 80}")
    
    return results  # Return all the pulses we created


def generate_pulse_for_week(week_key: str) -> Dict[str, Any]:
    """
    Generate pulse for a specific week
    
    Args:
        week_key: Week key (YYYY-MM-DD)
        
    Returns:
        Pulse data dictionary
    """
    logger.info("=" * 80)
    logger.info(f"Generating Pulse for Week: {week_key}")
    logger.info("=" * 80)
    
    themes_dir = settings.THEMES_DIR
    theme_file = os.path.join(themes_dir, f"themes_{week_key}.json")
    
    if not os.path.exists(theme_file):
        logger.error(f"Theme file not found: {theme_file}")
        return {
            "week_key": week_key,
            "error": "Theme file not found"
        }
    
    # Load theme data
    with open(theme_file, 'r', encoding='utf-8') as f:
        theme_data = json.load(f)
    
    # Generate pulse
    generator = WeeklyPulseGenerator()
    pulse_data = generator.generate_pulse(week_key, theme_data)
    
    return pulse_data


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Generate for specific week
        week_key = sys.argv[1]
        result = generate_pulse_for_week(week_key)
        if 'error' not in result:
            pulse = result.get('pulse', {})
            print(f"\n✅ Pulse generated for week {week_key}")
            print(f"Title: {pulse.get('title', 'N/A')}")
            print(f"Word count: {result.get('word_count', 'N/A')}")
        else:
            print(f"\n❌ Error: {result.get('error')}")
    else:
        # Generate for all weeks
        results = generate_all_pulses()
        print(f"\n✅ Generated {len([r for r in results if 'error' not in r])} pulses")

