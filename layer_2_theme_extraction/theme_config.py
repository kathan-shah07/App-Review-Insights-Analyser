"""
Theme configuration for stock broking app review classification
Defines the 5 allowed themes and their descriptions
"""

# Minimum review length (characters) - reviews shorter than this are ignored
MIN_REVIEW_LENGTH = 20

# Theme definitions with descriptions
THEMES = {
    "Trading Experience": {
        "description": "order placement, speed, charting, stock/ETF flows",
        "keywords": ["order", "trading", "buy", "sell", "chart", "execution", "speed", "stock", "ETF"]
    },
    "Mutual Funds & SIP Experience": {
        "description": "MF search, SIP setup, redemptions, portfolio insights",
        "keywords": ["mutual fund", "SIP", "MF", "redemption", "portfolio", "investment"]
    },
    "Payments, UPI & Settlements": {
        "description": "deposits, withdrawals, UPI reliability, T+1/T+0 settlement issues",
        "keywords": ["payment", "UPI", "deposit", "withdrawal", "settlement", "money", "transfer"]
    },
    "App Performance & Reliability": {
        "description": "crashes, loading time, login issues, downtime",
        "keywords": ["crash", "slow", "loading", "login", "error", "bug", "freeze", "downtime"]
    },
    "Support & Service Quality": {
        "description": "issue resolution, helpdesk, ticketing experience",
        "keywords": ["support", "customer service", "help", "ticket", "response", "service"]
    }
}

# Fallback theme when LLM assigns invalid theme
FALLBACK_THEME = "App Performance & Reliability"


def get_theme_list() -> list[str]:
    """
    Get list of all allowed theme names
    
    Returns:
        List of theme names
    """
    return list(THEMES.keys())


def get_theme_description(theme_name: str) -> str:
    """
    Get description for a specific theme
    
    Args:
        theme_name: Name of the theme
        
    Returns:
        Theme description, or empty string if theme not found
    """
    theme = THEMES.get(theme_name)
    if theme:
        return theme.get("description", "")
    return ""


def is_valid_theme(theme_name: str) -> bool:
    """
    Check if a theme name is valid
    
    Args:
        theme_name: Theme name to validate
        
    Returns:
        True if theme is valid, False otherwise
    """
    return theme_name in THEMES


def get_fallback_theme() -> str:
    """
    Get the fallback theme name
    
    Returns:
        Fallback theme name
    """
    return FALLBACK_THEME


def get_all_theme_descriptions() -> dict[str, str]:
    """
    Get all theme descriptions as a dictionary
    
    Returns:
        Dictionary mapping theme names to descriptions
    """
    return {
        theme_name: theme_data["description"]
        for theme_name, theme_data in THEMES.items()
    }

