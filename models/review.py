"""
Review data model
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import json


@dataclass
class Review:
    """Review data model"""
    review_id: str
    title: str
    text: str  # Cleaned and PII-redacted
    date: datetime
    platform: str  # "app_store" or "play_store"
    rating: Optional[int] = None  # 1-5 stars
    app_version: Optional[str] = None
    week_start_date: Optional[datetime] = None
    week_end_date: Optional[datetime] = None
    
    def __post_init__(self):
        """Calculate week dates if not provided"""
        if self.week_start_date is None or self.week_end_date is None:
            self._calculate_week_dates()
    
    def _calculate_week_dates(self):
        """Calculate week start and end dates based on review date"""
        # Week starts on Monday
        days_since_monday = self.date.weekday()
        self.week_start_date = self.date - timedelta(days=days_since_monday)
        self.week_start_date = self.week_start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        self.week_end_date = self.week_start_date + timedelta(days=6, hours=23, minutes=59, seconds=59)
    
    def to_dict(self) -> dict:
        """Convert review to dictionary for storage (minimal schema)"""
        return {
            "review_id": self.review_id,
            "text": self.text,
            "date": self.date.isoformat(),
            "platform": self.platform,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Review":
        """Create review from dictionary"""
        return cls(
            review_id=data["review_id"],
            title=data["title"],
            text=data["text"],
            date=datetime.fromisoformat(data["date"]),
            rating=data.get("rating"),
            app_version=data.get("app_version"),
            platform=data["platform"],
            week_start_date=datetime.fromisoformat(data["week_start_date"]) if data.get("week_start_date") else None,
            week_end_date=datetime.fromisoformat(data["week_end_date"]) if data.get("week_end_date") else None,
        )
    
    def to_json(self) -> str:
        """Convert review to JSON string"""
        return json.dumps(self.to_dict(), indent=2)
