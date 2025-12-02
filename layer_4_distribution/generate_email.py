"""
Entry point for generating and sending weekly email

This file takes the weekly pulse (summary) and turns it into an email
that can be sent to the team. It:
1. Loads the pulse we created in Layer 3
2. Uses AI to write a nice email (350 words or less)
3. Checks for personal information and removes it
4. Optionally sends the email via SMTP (like Gmail)

The email templates are saved so we can reuse them without regenerating.
"""
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional

from layer_4_distribution.email_drafter import EmailDrafter
from layer_4_distribution.pii_checker import PIIChecker
from layer_4_distribution.email_sender import EmailSender
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class EmailGenerator:
    """
    Generate and send weekly email
    
    This class handles the entire email workflow:
    - Drafting the email content
    - Checking for personal information
    - Sending the email
    - Saving templates for reuse
    """
    
    def __init__(self):
        """Initialize email generator - Set up all the tools we need"""
        self.drafter = EmailDrafter()      # Writes the email content using AI
        self.pii_checker = PIIChecker()   # Checks for personal info (emails, phones)
        self.sender = EmailSender()       # Sends the email via SMTP
        # Set up paths to where we store pulses and emails
        self.pulses_dir = os.path.join(settings.DATA_DIR, "pulses")
        self.emails_dir = os.path.join(settings.DATA_DIR, "emails")
        os.makedirs(self.emails_dir, exist_ok=True)  # Create emails folder if it doesn't exist
    
    def generate_and_send_email(self, week_key: str, 
                                 send: bool = True,
                                 regenerate: bool = False) -> Dict[str, Any]:
        """
        Generate and optionally send email for a week - Main function
        
        This function:
        1. Checks if we already have an email template for this week (saves time!)
        2. If not, loads the pulse and uses AI to write an email
        3. Checks for personal information and removes it
        4. Saves the template for future use
        5. Optionally sends the email
        
        Args:
            week_key: Week key (YYYY-MM-DD) - which week to process
            send: Whether to actually send the email (default: True)
                  Set to False for preview mode (safe testing)
            regenerate: Force regeneration even if template exists (default: False)
                       Set to True if you want to rewrite the email
        
        Returns:
            Dictionary with email generation and send results
        """
        logger.info(f"Generating email for week {week_key}")
        
        # ============================================================
        # Check if email template already exists
        # ============================================================
        # We save email templates so we don't have to regenerate them
        # This saves time and API costs
        email_template_file = os.path.join(self.emails_dir, f"email_{week_key}.json")
        
        if not regenerate and os.path.exists(email_template_file):
            # We already have a template! Load it instead of regenerating
            logger.info(f"Loading stored email template from {email_template_file}")
            try:
                with open(email_template_file, 'r', encoding='utf-8') as f:
                    email_template = json.load(f)
                
                # Extract the email content
                subject = email_template.get('subject', '')
                email_body = email_template.get('email_body', '')
                detected_pii = email_template.get('pii_detected', [])
                
                logger.info(f"Loaded stored template: {len(email_body.split())} words")
                
            except Exception as e:
                # If loading fails, we'll regenerate it
                logger.warning(f"Error loading email template: {e}, regenerating...")
                email_template = None
        else:
            email_template = None  # Need to generate a new one
        
        # ============================================================
        # Generate email template if not loaded
        # ============================================================
        if email_template is None:
            # Load the pulse (weekly summary) we created in Layer 3
            pulse_file = os.path.join(self.pulses_dir, f"pulse_{week_key}.json")
            
            if not os.path.exists(pulse_file):
                # Can't create email without the pulse!
                error_msg = f"Pulse file not found: {pulse_file}"
                logger.error(error_msg)
                return {
                    "week_key": week_key,
                    "success": False,
                    "error": error_msg
                }
            
            try:
                with open(pulse_file, 'r', encoding='utf-8') as f:
                    pulse_data = json.load(f)
            except Exception as e:
                error_msg = f"Error loading pulse file: {e}"
                logger.error(error_msg)
                return {
                    "week_key": week_key,
                    "success": False,
                    "error": error_msg
                }
            
            # Use AI to draft the email body
            # This converts the pulse into a nice email format (350 words or less)
            logger.info("Drafting email body with LLM...")
            email_body = self.drafter.draft_email_body(pulse_data)
            
            # Generate a subject line (like "Weekly Product Pulse – Groww (2025-11-24–2025-11-30)")
            week_start = pulse_data.get('week_start_date', week_key)
            week_end = pulse_data.get('week_end_date', '')
            subject = self.drafter.generate_subject_line(week_start, week_end)
            
            # Check for personal information (PII) and remove it
            # This is important for privacy - we don't want to send emails with
            # phone numbers or email addresses in them
            logger.info("Checking for PII...")
            email_body, detected_pii = self.pii_checker.check_and_remove_pii(email_body, mask=True)
            subject, subject_has_pii = self.pii_checker.check_subject_line(subject)
            
            if detected_pii or subject_has_pii:
                logger.warning(f"PII detected and removed: {len(detected_pii)} instances")
            
            # Save the email template so we can reuse it later
            email_template = {
                "week_key": week_key,
                "week_start_date": week_start,
                "week_end_date": week_end,
                "generated_at": datetime.now().isoformat(),
                "subject": subject,
                "email_body": email_body,
                "word_count": len(email_body.split()),
                "pii_detected": detected_pii,
                "pii_count": len(detected_pii)
            }
            
            self._save_email_template(week_key, email_template)
            logger.info(f"Saved email template to {email_template_file}")
        
        # ============================================================
        # Send email if requested
        # ============================================================
        # By default, this is in preview mode (send=False) for safety
        # You need to explicitly use --send flag to actually send emails
        send_result = None
        if send:
            logger.info("Sending email...")
            send_result = self.sender.send_email(subject, email_body)
            self.sender.log_send_status(week_key, send_result)
        else:
            logger.info("Email generation complete (not sending)")
        
        return {
            "week_key": week_key,
            "success": True,
            "subject": subject,
            "email_body": email_body,
            "word_count": email_template.get('word_count', len(email_body.split())),
            "pii_detected": len(email_template.get('pii_detected', [])),
            "send_result": send_result,
            "template_source": "stored" if not regenerate and os.path.exists(email_template_file) else "generated"
        }
    
    def generate_email_preview(self, week_key: str, regenerate: bool = False) -> Dict[str, Any]:
        """
        Generate email preview without sending
        
        Args:
            week_key: Week key (YYYY-MM-DD)
            regenerate: Force regeneration even if template exists
            
        Returns:
            Dictionary with email preview
        """
        return self.generate_and_send_email(week_key, send=False, regenerate=regenerate)
    
    def _save_email_template(self, week_key: str, email_template: Dict[str, Any]):
        """
        Save email template to JSON file
        
        Args:
            week_key: Week key
            email_template: Email template dictionary
        """
        filename = os.path.join(self.emails_dir, f"email_{week_key}.json")
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(email_template, f, indent=2, ensure_ascii=False, default=str)
            logger.info(f"Saved email template to {filename}")
        except Exception as e:
            logger.error(f"Error saving email template to {filename}: {e}", exc_info=True)
    
    def load_email_template(self, week_key: str) -> Optional[Dict[str, Any]]:
        """
        Load stored email template
        
        Args:
            week_key: Week key
            
        Returns:
            Email template dictionary or None if not found
        """
        filename = os.path.join(self.emails_dir, f"email_{week_key}.json")
        
        if not os.path.exists(filename):
            return None
        
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading email template from {filename}: {e}")
            return None


def generate_and_send_all_emails(send: bool = False, regenerate: bool = False) -> list:
    """
    Generate and optionally send emails for all available weeks
    
    Args:
        send: Whether to actually send emails (default: False for safety)
        
    Returns:
        List of email generation results
    """
    logger.info("=" * 80)
    logger.info("Starting Email Generation Workflow")
    logger.info("=" * 80)
    logger.info(f"Send mode: {'ENABLED' if send else 'PREVIEW ONLY'}")
    logger.info(f"Regenerate: {'YES' if regenerate else 'NO (using stored templates if available)'}")
    logger.info("=" * 80)
    
    pulses_dir = os.path.join(settings.DATA_DIR, "pulses")
    
    if not os.path.exists(pulses_dir):
        logger.error(f"Pulses directory not found: {pulses_dir}")
        return []
    
    # Find all pulse files
    pulse_files = [
        f for f in os.listdir(pulses_dir)
        if f.startswith('pulse_') and f.endswith('.json')
    ]
    
    if not pulse_files:
        logger.warning("No pulse files found")
        return []
    
    logger.info(f"Found {len(pulse_files)} weeks to process")
    
    generator = EmailGenerator()
    results = []
    
    for pulse_file in sorted(pulse_files):
        week_key = pulse_file.replace('pulse_', '').replace('.json', '')
        
        try:
            logger.info(f"\n{'=' * 80}")
            logger.info(f"Processing week: {week_key}")
            logger.info(f"{'=' * 80}")
            
            result = generator.generate_and_send_email(week_key, send=send, regenerate=regenerate)
            results.append(result)
            
        except Exception as e:
            logger.error(f"Error processing week {week_key}: {e}", exc_info=True)
            results.append({
                "week_key": week_key,
                "success": False,
                "error": str(e)
            })
    
    successful = len([r for r in results if r.get('success')])
    logger.info(f"\n{'=' * 80}")
    logger.info(f"Email Generation Summary")
    logger.info(f"{'=' * 80}")
    logger.info(f"Processed: {successful}/{len(pulse_files)} weeks successfully")
    if send:
        sent = len([r for r in results if r.get('send_result', {}).get('success')])
        logger.info(f"Sent: {sent}/{len(pulse_files)} emails")
    logger.info(f"{'=' * 80}")
    
    return results


if __name__ == "__main__":
    import sys
    
    # Check for flags
    send = "--send" in sys.argv or "-s" in sys.argv
    regenerate = "--regenerate" in sys.argv or "-r" in sys.argv
    
    if len(sys.argv) > 1 and sys.argv[1] not in ["--send", "-s", "--regenerate", "-r"]:
        # Generate for specific week
        week_key = sys.argv[1]
        generator = EmailGenerator()
        result = generator.generate_and_send_email(week_key, send=send, regenerate=regenerate)
        
        if result.get('success'):
            print(f"\n✅ Email {'generated' if regenerate or result.get('template_source') == 'generated' else 'loaded'} for week {week_key}")
            print(f"Source: {result.get('template_source', 'unknown')}")
            print(f"Subject: {result.get('subject')}")
            print(f"Word count: {result.get('word_count')}")
            if result.get('pii_detected', 0) > 0:
                print(f"⚠️  PII detected: {result.get('pii_detected')} instances")
            if send and result.get('send_result', {}).get('success'):
                print(f"📧 Email sent successfully")
            elif send:
                print(f"❌ Email send failed: {result.get('send_result', {}).get('error')}")
        else:
            print(f"\n❌ Error: {result.get('error')}")
    else:
        # Generate for all weeks
        results = generate_and_send_all_emails(send=send, regenerate=regenerate)
        if send:
            print(f"\n✅ Generated and sent {len([r for r in results if r.get('send_result', {}).get('success')])} emails")
        else:
            print(f"\n✅ Generated {len([r for r in results if r.get('success')])} email previews (not sent)")

