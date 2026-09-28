import os
from pathlib import Path
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PROFILE_DIR = BASE_DIR / "browser_profile"
DATA_DIR.mkdir(parents=True, exist_ok=True)
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "bestresponse.db"

class Settings(BaseModel):
    app_name: str = "BestResponse AI Multi-LLM Aggregator"
    host: str = "127.0.0.1"
    port: int = 8000
    profile_dir: Path = PROFILE_DIR
    db_path: Path = DB_PATH
    
    # Provider URLs
    chatgpt_url: str = "https://chatgpt.com/"
    claude_url: str = "https://claude.ai/new"
    gemini_url: str = "https://gemini.google.com/app"
    glm_url: str = "https://chat.z.ai/"
    
    # Automation timings (in seconds)
    page_load_timeout: int = 45
    response_generation_timeout: int = 150
    idle_text_stabilize_seconds: float = 3.0
    
    # Browser behavior
    headless: bool = False  # Headed browser by default to seamlessly bypass Cloudflare & bot challenges
    slow_mo: int = 50       # Slow motion in ms to simulate human interaction

settings = Settings()
