"""
Configuration Management for build-kg
Loads settings from environment variables with defaults.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Search for .env file: CWD first, then project root (two levels up from this file)
_env_candidates = [
    Path.cwd() / '.env',
    Path(__file__).resolve().parent.parent.parent / '.env',
]
for env_path in _env_candidates:
    if env_path.exists():
        load_dotenv(env_path)
        break

# Database Configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', '5432')),
    'database': os.getenv('DB_NAME', 'buildkg'),
    'user': os.getenv('DB_USER', 'buildkg'),
    'password': os.getenv('DB_PASSWORD', ''),
}

# OpenAI Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')

# AGE Graph Configuration
AGE_GRAPH_NAME = os.getenv('AGE_GRAPH_NAME', 'reg_ca')

# Domain Profile Configuration
DOMAIN = os.getenv('DOMAIN', 'default')

# Parser Configuration
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '10'))
MAX_WORKERS = int(os.getenv('MAX_WORKERS', '3'))
RATE_LIMIT_DELAY = float(os.getenv('RATE_LIMIT_DELAY', '1.0'))

def validate_config():
    """Validate required configuration is present."""
    errors = []

    if not DB_CONFIG['password']:
        errors.append("DB_PASSWORD is required")

    if not OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY is required")

    if errors:
        raise ValueError(f"Configuration errors: {', '.join(errors)}")

    return True
