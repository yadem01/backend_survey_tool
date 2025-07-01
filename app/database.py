# app/database.py
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# Lade Umgebungsvariablen aus der .env Datei im Projekt-Root
# (stellt sicher, dass es auch funktioniert, wenn database.py indirekt importiert wird)
dotenv_path = os.path.join(
    os.path.dirname(__file__), "..", ".env"
)  # Pfad zur .env im Root
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:  # Fallback, falls .env nicht im Root ist, sondern neben database.py (weniger üblich)
    load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL is None:
    print(
        "WARNUNG: DATABASE_URL nicht in Umgebungsvariablen gefunden! Fallback auf lokale SQLite-DB."
    )
    # Fallback auf eine SQLite-Datenbank, wenn keine DATABASE_URL gesetzt ist
    # Passe den Pfad an, falls deine SQLite-DB woanders liegen soll oder anders heißt
    # Für WSL ist ein Pfad innerhalb des WSL-Dateisystems am besten, z.B. relativ zum Projekt
    sqlite_db_path = os.path.join(os.path.dirname(__file__), "survey_app_fallback.db")
    DATABASE_URL = f"sqlite+aiosqlite:///{sqlite_db_path}"


print(f"DEBUG [database.py]: Using DATABASE_URL: {DATABASE_URL}")

# echo=True gibt alle SQL-Statements aus, die SQLAlchemy generiert. Nützlich für Debugging.
# In Produktion auf False setzen für weniger Log-Output.
engine = create_async_engine(DATABASE_URL, echo=True)

AsyncSessionFactory = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, class_=AsyncSession
)

Base = declarative_base()


async def get_db_session() -> AsyncSession:
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()  # Commit am Ende, wenn alles gut ging
        except Exception as e:
            await session.rollback()  # Rollback bei Fehlern
            raise e
        finally:
            await session.close()


async def create_db_and_tables():
    """
    Diese Funktion ist jetzt nicht mehr für die Erstellung von Tabellen zuständig,
    da dies von Alembic übernommen wird. Sie kann für andere initiale DB-Setup-Aufgaben
    verwendet werden, falls nötig, oder leer bleiben.
    """
    print("Datenbanktabellen würden hier erstellt (jetzt durch Alembic verwaltet).")
    pass
