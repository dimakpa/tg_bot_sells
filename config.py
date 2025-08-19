import os
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    # Bot settings
    bot_token: str = "1356430120:AAGRBuqrPMGEkLiR1gmR0aC3ECXGsVs4nZw"
    
    # Database settings
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot_database.db")
    
    # Admin settings
    admin_user_ids: list[int] = []
    
    # Timezone settings
    default_timezone: str = "Europe/Moscow"
    
    # Report settings
    max_report_days: int = 365
    max_transactions_per_report: int = 10000
    
    # Backup settings
    backup_enabled: bool = True
    backup_retention_days: int = 30
    
    class Config:
        env_file = ".env"


settings = Settings() 