import os
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# Annahme: .env Datei ist im Hauptverzeichnis des Backends (eine Ebene über 'app')
dotenv_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=dotenv_path)

DEFAULT_SQLITE_PATH = Path(__file__).resolve().parent / "survey_app.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DEFAULT_SQLITE_PATH}")

print(f"DEBUG: Using DATABASE_URL: {DATABASE_URL}")  # Debug-Ausgabe für den Pfad

engine = create_async_engine(
    DATABASE_URL, echo=False
)  # Echo auf False für weniger Logs bei Background-Tasks
AsyncSessionFactory = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)
Base = declarative_base()


# Hilfsfunktion, um eine Datenbank-Session zu erhalten (Dependency für FastAPI)
async def get_db_session() -> AsyncSession:
    """
    Dependency to get an async database session.
    Ensures the session is closed after the request.
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()  # Änderungen committen, wenn alles gut ging
        except Exception:
            await session.rollback()  # Rollback bei Fehlern
            raise
        finally:
            await session.close()  # Session immer schließen


# Funktion zum Erstellen der Tabellen (optional, für Initialisierung)
async def create_db_and_tables():
    """Creates database tables based on the defined models."""
    async with engine.begin() as conn:
        # Löscht alle Tabellen (nur für Entwicklung!)
        # await conn.run_sync(Base.metadata.drop_all)
        # Erstellt alle Tabellen
        await conn.run_sync(Base.metadata.create_all)
    print("Datenbanktabellen erstellt (falls nicht vorhanden).")
