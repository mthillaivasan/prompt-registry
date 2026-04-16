import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./prompt_registry.db")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
