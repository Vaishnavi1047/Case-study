import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# JWT Settings
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-moveinsync-change-in-prod")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

# LLM Settings
USE_FAKE_LLM = os.getenv("USE_FAKE_LLM", "true").lower() in ("true", "1", "yes")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Default reference / simulation time (e.g. today at 17:30 / 5:30 PM)
# Used for deterministic testing of cut-off times.
DEFAULT_SIMULATED_TIME = os.getenv("SIMULATED_TIME", "2026-11-24 17:30:00")

def get_current_time(override: str | None = None) -> datetime:
    """Returns datetime object for current or simulated operational time."""
    time_str = override or DEFAULT_SIMULATED_TIME
    try:
        return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.now()

