import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE)

class Settings:
    BASE_DIR: Path = BASE_DIR
    PROFILE_DIR: Path = BASE_DIR / ".zalo_profile"
    DATA_DIR: Path = BASE_DIR / "data"
    
    # AI / Gemini
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    GEMINI_TIMEOUT_SECONDS: int = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "30"))
    
    # Supabase
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_API_KEY_SERVICE_ROLE: str = os.getenv("SUPABASE_API_KEY_SERVICE_ROLE", "")
    SUPABASE_PUBLISHABLE_KEY: str = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
    SUPABASE_SECRET_KEY: str = os.getenv("SUPABASE_SECRET_KEY", "")
    SUPABASE_URL_POSTGRES: str = os.getenv("SUPABASE_URL_POSTGRES", "")
    
    # Server & Port (Supports Render's $PORT)
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    HEADLESS: bool = os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes")

settings = Settings()

