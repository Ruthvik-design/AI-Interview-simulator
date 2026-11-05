import os
from pathlib import Path

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
DB = Path(os.getenv("INTERVIEW_DB", Path(__file__).with_name("interview_simulator.db")))
MAX_QUESTIONS = 10
FOLLOWUP_BELOW = 7.0
SESSION_SECONDS = 7 * 24 * 3600
KEYS = ("relevance", "completeness", "clarity", "technical_understanding", "communication")
LOCKS = {}
