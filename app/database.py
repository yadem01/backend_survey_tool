import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# Lade Umgebungsvariablen aus der .env Datei
load_dotenv()

# Datenbank-URL aus Umgebungsvariable lesen (Fallback auf SQLite)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./survey_app.db")

# Erstelle die asynchrone SQLAlchemy Engine
# `echo=True` gibt SQL-Abfragen in der Konsole aus (nützlich für Debugging)
engine = create_async_engine(DATABASE_URL, echo=True)

# Erstelle eine Factory für asynchrone Sessions
# expire_on_commit=False verhindert, dass Objekte nach einem Commit ungültig werden
AsyncSessionFactory = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Basisklasse für deklarative Modelle
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
            await session.commit() # Änderungen committen, wenn alles gut ging
        except Exception:
            await session.rollback() # Rollback bei Fehlern
            raise
        finally:
            await session.close() # Session immer schließen

# Funktion zum Erstellen der Tabellen (optional, für Initialisierung)
async def create_db_and_tables():
    """Creates database tables based on the defined models."""
    async with engine.begin() as conn:
        # Löscht alle Tabellen (nur für Entwicklung!)
        # await conn.run_sync(Base.metadata.drop_all)
        # Erstellt alle Tabellen
        await conn.run_sync(Base.metadata.create_all)
    print("Datenbanktabellen erstellt (falls nicht vorhanden).")