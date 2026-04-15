import os
from dotenv import load_dotenv

# Cargar .env
load_dotenv()

class Config:
    # Seguridad
    SECRET_KEY = os.getenv("SECRET_KEY", "dev")

    # Base de datos (Neon o SQLite fallback)
    DATABASE_URL = os.getenv("DATABASE_URL")

    # (opcional si algún día usas SQLAlchemy)
    SQLALCHEMY_DATABASE_URI = DATABASE_URL or "sqlite:///orion.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # APIs
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
    GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")