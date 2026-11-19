import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "EventSphere"
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "eventsphere-super-secure-secret-key-2026-viva")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    
    # SQLite for local dev, PostgreSQL for production
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./eventsphere.db")
    
    # Timing & agent settings
    CART_HOLD_DURATION_SECONDS: int = 300       # 5 minutes for attendee checkout
    WAITLIST_HOLD_DURATION_SECONDS: int = 300   # 5 minutes for released seat claim
    WAITLIST_SWEEP_INTERVAL_SECONDS: int = 10   # Proactive timer sweep interval
    VENUE_TURNAROUND_BUFFER_MINUTES: int = 60   # Required buffer between activities
    TICKET_MAX_PER_BOOKING: int = 6             # Agent decision rule: max tickets per booking
    
    # Refund rules (hours prior to event start)
    REFUND_FULL_HOURS: int = 48                 # >= 48h -> 100% refund
    REFUND_HALF_HOURS: int = 24                 # >= 24h & < 48h -> 50% refund

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()
