import os
from dotenv import load_dotenv

# Cargar .env si estás en entorno local
env = os.getenv("ENV", "local")
if env == "local":
    load_dotenv(".env.local")


class Config:
    # Seguridad
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'd16f2bfa7491b82b8f9e30cf60eac02c82c648b1a93f7d9c671a3973d7eb69e5'

    # Configuración PostgreSQL
    POSTGRES_HOST = os.environ.get("POSTGRES_HOST") or "localhost"
    POSTGRES_USER = os.environ.get("POSTGRES_USER") or "alucard"
    POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD") or ""
    POSTGRES_DB = os.environ.get("POSTGRES_DB") or "orion"
    POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT") or 5432)
    DATABASE_URL = os.environ.get("DATABASE_URL")

    # SQLAlchemy Database URI para PostgreSQL o SQLite local
    SQLALCHEMY_DATABASE_URI = DATABASE_URL or f"sqlite:///orion.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Gemini API Key
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
    GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI")
