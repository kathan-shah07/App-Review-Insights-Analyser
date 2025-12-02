"""
Layer 4: Distribution & Feedback
- Email Content Drafter (LLM-based email generation)
- PII Checker (detection and removal)
- Email Sender (SMTP/Gmail)
- Email Generator (orchestrates workflow)
"""
from .email_drafter import EmailDrafter
from .pii_checker import PIIChecker
from .email_sender import EmailSender
from .generate_email import EmailGenerator, generate_and_send_all_emails

__all__ = [
    'EmailDrafter',
    'PIIChecker',
    'EmailSender',
    'EmailGenerator',
    'generate_and_send_all_emails',
]


