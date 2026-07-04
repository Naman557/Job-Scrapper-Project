import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# SMTP Config
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER", "")

# Scraper Config
HEADLESS_MODE = os.getenv("HEADLESS_MODE", "True").lower() in ("true", "1", "yes")
MAX_JOBS_PER_PORTAL = int(os.getenv("MAX_JOBS_PER_PORTAL", 10))
LOOP_INTERVAL = int(os.getenv("LOOP_INTERVAL", 3600))
MAX_AGE_DAYS = int(os.getenv("MAX_AGE_DAYS", 14))

def validate_config():
    """
    Validates that the required environment variables are set.
    """
    missing = []
    if not SMTP_USERNAME or SMTP_USERNAME == "your_email@gmail.com":
        missing.append("SMTP_USERNAME")
    if not SMTP_PASSWORD or SMTP_PASSWORD == "your_app_password":
        missing.append("SMTP_PASSWORD")
    if not EMAIL_RECEIVER or EMAIL_RECEIVER == "recipient_email@gmail.com":
        missing.append("EMAIL_RECEIVER")
    
    if missing:
        print(f"Warning: The following environment variables are missing or use default placeholders: {', '.join(missing)}")
        print("Please check your .env file before running email tasks.")
        return False
    return True
