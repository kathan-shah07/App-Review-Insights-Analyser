"""
Email sending automation via SMTP
Supports Gmail and other SMTP servers
"""
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional, Dict, Any

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class EmailSender:
    """Send emails via SMTP"""
    
    def __init__(self):
        """Initialize email sender with settings (Gmail-ready)"""
        # Gmail SMTP settings (default)
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))  # 587 for TLS, 465 for SSL
        self.smtp_username = os.getenv("SMTP_USERNAME", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")  # Use Gmail App Password
        self.from_email = os.getenv("FROM_EMAIL", self.smtp_username)
        self.to_email = os.getenv("TO_EMAIL", "")
        self.use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
        
        # Validate Gmail configuration
        if self.smtp_server == "smtp.gmail.com" and self.smtp_username:
            if not self.smtp_password:
                logger.warning("Gmail requires an App Password (not your regular password). See README for setup instructions.")
    
    def send_email(self, subject: str, body: str, 
                   to_email: Optional[str] = None,
                   from_email: Optional[str] = None) -> Dict[str, Any]:
        """
        Send email via SMTP
        
        Args:
            subject: Email subject
            body: Email body (plain text)
            to_email: Recipient email (uses default if not provided)
            from_email: Sender email (uses default if not provided)
            
        Returns:
            Dictionary with send status and metadata
        """
        to_email = to_email or self.to_email
        from_email = from_email or self.from_email
        
        if not to_email:
            error_msg = "No recipient email configured"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }
        
        if not self.smtp_username or not self.smtp_password:
            error_msg = "SMTP credentials not configured"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }
        
        try:
            logger.info(f"Sending email to {to_email}")
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = from_email
            msg['To'] = to_email
            msg['Subject'] = subject
            
            # Add body
            msg.attach(MIMEText(body, 'plain'))
            
            # Connect and send
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {to_email}")
            
            return {
                "success": True,
                "to": to_email,
                "from": from_email,
                "subject": subject,
                "timestamp": datetime.now().isoformat(),
                "word_count": len(body.split())
            }
            
        except smtplib.SMTPAuthenticationError as e:
            error_msg = f"SMTP authentication failed: {e}"
            logger.error(error_msg)
            
            # Gmail-specific help message
            if self.smtp_server == "smtp.gmail.com":
                logger.error("Gmail authentication failed. Common issues:")
                logger.error("  1. Make sure you're using an App Password (not your regular Gmail password)")
                logger.error("  2. Enable 2-Step Verification in your Google Account")
                logger.error("  3. Generate an App Password: https://myaccount.google.com/apppasswords")
                logger.error("  4. Use the 16-character App Password in SMTP_PASSWORD")
            
            return {
                "success": False,
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }
        except smtplib.SMTPException as e:
            error_msg = f"SMTP error: {e}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            error_msg = f"Unexpected error sending email: {e}"
            logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }
    
    def log_send_status(self, week_key: str, result: Dict[str, Any]):
        """
        Log email send status for traceability
        
        Args:
            week_key: Week key
            result: Send result dictionary
        """
        if result.get("success"):
            logger.info(f"Email sent for week {week_key}:")
            logger.info(f"  To: {result.get('to')}")
            logger.info(f"  Subject: {result.get('subject')}")
            logger.info(f"  Timestamp: {result.get('timestamp')}")
            logger.info(f"  Word count: {result.get('word_count')}")
        else:
            logger.error(f"Email send failed for week {week_key}: {result.get('error')}")

