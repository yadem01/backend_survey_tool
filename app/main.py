import os
import uuid  # Für eindeutige Dateinamen
import shutil  # Für Dateioperationen
from pathlib import Path  # Für Pfadoperationen

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    UploadFile,
    File,
    status,
    BackgroundTasks,
)
from fastapi.staticfiles import StaticFiles  # Für statische Dateien
from fastapi.middleware.cors import CORSMiddleware  # Für Frontend-Zugriff
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func  # Für DateTime Default

from . import models
from . import schemas
from .database import get_db_session, create_db_and_tables, engine, AsyncSessionFactory
from contextlib import asynccontextmanager

# BASE_DIR zeigt jetzt auf den 'app'-Ordner, wenn __file__ aus app/main.py kommt
# UPLOAD_DIR wird relativ dazu oder absolut definiert.
# Wenn UPLOAD_DIR im Projekt-Root (neben 'app') sein soll
PROJECT_ROOT_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = PROJECT_ROOT_DIR / "uploads/images"
STATIC_FILES_ROUTE = "/static_images"  # Dieser Pfad bleibt relativ zur Domain
BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000")


# --- Lifecycle Events (unverändert) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Anwendung startet...")
    # Erstelle Upload-Verzeichnis, falls nicht vorhanden
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Upload-Verzeichnis sichergestellt: {UPLOAD_DIR.resolve()}")
    await create_db_and_tables()  # Nur bei Bedarf einkommentieren
    yield
    print("Anwendung fährt herunter...")
    await engine.dispose()


# --- FastAPI App Instanz ---
app = FastAPI(title="Survey Tool Backend", lifespan=lifespan)

# --- CORS Middleware (WICHTIG für Frontend-Zugriff) ---
origins = [
    "http://127.0.0.1:5173",  # Deine Frontend Dev URL (passe Port ggf. an)
    "http://localhost:5173",
    # "https://deine-live-frontend-url.com" # Später hinzufügen
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static Files Mounten, um Bilder auszuliefern
# Stellt den Inhalt von UPLOAD_DIR unter dem Pfad STATIC_FILES_ROUTE bereit
app.mount(STATIC_FILES_ROUTE, StaticFiles(directory=UPLOAD_DIR), name="static_images")
print(
    f"Statisches Verzeichnis '{UPLOAD_DIR}' wird unter '{STATIC_FILES_ROUTE}' bereitgestellt."
)


async def perform_image_cleanup():
    print("Hintergrund-Task: Starte Bild-Cleanup...")
    deleted_files_list = []
    message = "Keine verwaisten Bilder zum Löschen gefunden."

    async with AsyncSessionFactory() as session:
        try:
            # 1. Alle verwendeten image_urls aus der Datenbank holen
            stmt = select(models.SurveyElement.image_url).where(
                models.SurveyElement.image_url.isnot(None)
            )
            result = await session.execute(stmt)
            # Wichtig: Die URLs in der DB sind volle URLs (z.B. http://server/static_images/bild.jpg)
            used_image_full_urls = {url for (url,) in result.all() if url}
            print(
                f"Hintergrund-Task: Verwendete Bild-URLs (aus DB): {len(used_image_full_urls)}"
            )
            # if used_image_full_urls: print(f"Beispiel verwendete URL: {list(used_image_full_urls)[0]}")

            # 2. Alle Dateien im Upload-Verzeichnis auflisten
            if not UPLOAD_DIR.exists():
                print("Hintergrund-Task: Upload-Verzeichnis nicht gefunden.")
                return

            stored_files = [f for f in UPLOAD_DIR.iterdir() if f.is_file()]
            print(
                f"Hintergrund-Task: Gespeicherte Dateien im Upload-Ordner: {len(stored_files)}"
            )

            # 3. Vergleichen und Löschen
            for file_path_obj in stored_files:
                # Konstruiere die *volle URL*, wie sie in der DB gespeichert sein sollte
                # basierend auf dem Dateinamen im Upload-Ordner.
                expected_full_url_in_db = (
                    f"{BACKEND_BASE_URL}{STATIC_FILES_ROUTE}/{file_path_obj.name}"
                )

                if expected_full_url_in_db not in used_image_full_urls:
                    try:
                        file_path_obj.unlink()
                        deleted_files_list.append(file_path_obj.name)
                        print(
                            f"Hintergrund-Task: Gelöscht (nicht verwendet): {file_path_obj.name} (erwartete URL: {expected_full_url_in_db})"
                        )
                    except Exception as e:
                        print(
                            f"Hintergrund-Task: Fehler beim Löschen von {file_path_obj.name}: {e}"
                        )
                # else:
                #     print(f"Hintergrund-Task: Behalten (in Verwendung): {file_path_obj.name} (URL: {expected_full_url_in_db})")

            if deleted_files_list:
                message = f"{len(deleted_files_list)} verwaiste Bilder im Hintergrund gelöscht."
            print(f"Hintergrund-Task: {message}")

        except Exception as e:
            print(f"Hintergrund-Task: Schwerwiegender Fehler im Cleanup-Prozess: {e}")


# --- API Endpunkte ---
@app.get("/")
async def read_root():
    return {"message": "Willkommen zum Survey Tool Backend!"}


# Endpunkt für Bild-Upload
@app.post("/api/upload/image", response_model=schemas.ImageUploadResponse)
async def upload_image(file: UploadFile = File(...)):
    """
    Nimmt eine Bilddatei entgegen, speichert sie im Dateisystem
    und gibt den relativen Pfad zurück.
    """
    # Erlaubte Dateitypen prüfen (Beispiel)
    allowed_mime_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_mime_types:
        raise HTTPException(status_code=400, detail="Ungültiger Dateityp.")

    try:
        # Eindeutigen Dateinamen generieren
        file_extension = Path(file.filename).suffix
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = UPLOAD_DIR / unique_filename
        relative_url_path = f"{BACKEND_BASE_URL}{STATIC_FILES_ROUTE}/{unique_filename}"  # Pfad für Frontend

        print(f"Versuche Bild zu speichern unter: {file_path}")

        # Datei speichern (asynchron)
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        print(f"Bild erfolgreich gespeichert: {file_path}")
        # Relative URL zurückgeben
        return schemas.ImageUploadResponse(file_path=relative_url_path)

    except Exception as e:
        print(f"Fehler beim Speichern des Bildes: {e}")
        raise HTTPException(status_code=500, detail="Fehler beim Speichern des Bildes.")
    finally:
        # Schließe die temporäre Datei (wichtig!)
        await file.close()


# Endpunkt zum Speichern von Umfrageergebnissen
@app.post("/api/results", response_model=schemas.SurveyResultResponse, status_code=201)
async def save_survey_results(
    result_data: schemas.SurveyResultCreate, db: AsyncSession = Depends(get_db_session)
):
    """Speichert Umfrageergebnisse (vereinfacht)."""
    print("Empfangene Ergebnisdaten:", result_data.model_dump())
    survey_id_example = 1  # Annahme

    new_participant = models.SurveyParticipant(
        survey_id=survey_id_example,
        prolific_pid=result_data.prolific_pid,
        consent_given=result_data.consent_given,
        completed=True,
        end_time=func.now(),
    )
    db.add(new_participant)
    await db.flush()
    await db.refresh(new_participant)
    print(f"Teilnehmer erstellt mit ID: {new_participant.id}")

    responses_to_add = []
    for question_id_str, value in result_data.answers.items():
        try:
            question_id = int(question_id_str)
            new_response = models.Response(
                participant_id=new_participant.id,
                survey_element_id=question_id,
                response_value=value,
            )
            responses_to_add.append(new_response)
        except ValueError:
            print(f"Warnung: Ungültige Question ID '{question_id_str}' übersprungen.")
            continue

    if responses_to_add:
        db.add_all(responses_to_add)
        print(f"{len(responses_to_add)} Antworten hinzugefügt.")

    return schemas.SurveyResultResponse(participant_id=new_participant.id)


# Endpunkt zum Speichern einer Umfrage-Definition
@app.post("/api/surveys", response_model=schemas.SurveyCreateResponse, status_code=201)
async def create_survey(
    survey_in: schemas.SurveyCreate,  # Nimmt Daten gemäß SurveyCreate Schema entgegen
    background_tasks: BackgroundTasks,  # Für Hintergrund-Tasks
    db: AsyncSession = Depends(get_db_session),
):
    """
    Erstellt eine neue Umfrage und deren Elemente in der Datenbank.
    """
    print("Empfangene Umfragedaten:", survey_in.model_dump())

    # 1. Erstelle den Haupteintrag für die Umfrage
    new_survey = models.Survey(
        title=survey_in.survey_title,
        description=survey_in.survey_description,
        config=survey_in.config.model_dump(),  # Speichere config als JSON
    )
    db.add(new_survey)
    await db.flush()  # Spüle, um die ID der neuen Umfrage zu bekommen
    await db.refresh(new_survey)
    print(f"Survey erstellt mit ID: {new_survey.id}")

    # 2. Erstelle die Elemente (Fragen etc.) und verknüpfe sie
    elements_to_add = []
    for element_data in survey_in.questions:
        # Konvertiere Pydantic-Schema zu Dict für SQLAlchemy-Modell
        element_dict = element_data.model_dump()
        # Füge die survey_id hinzu
        element_dict["survey_id"] = new_survey.id
        # Erstelle SQLAlchemy-Objekt
        new_element = models.SurveyElement(**element_dict)
        elements_to_add.append(new_element)

    if elements_to_add:
        db.add_all(elements_to_add)
        print(f"{len(elements_to_add)} Survey-Elemente hinzugefügt.")

    # HIER WIRD DER CLEANUP-TASK HINZUGEFÜGT
    background_tasks.add_task(perform_image_cleanup)
    print(f"Bild-Cleanup-Task für Survey ID {new_survey.id} im Hintergrund gestartet.")

    return schemas.SurveyCreateResponse(survey_id=new_survey.id)


# Endpunkt zum Abrufen einer Umfrage-Definition
@app.get("/api/surveys/{survey_id}", response_model=schemas.SurveyResponse)
async def get_survey(survey_id: int, db: AsyncSession = Depends(get_db_session)):
    """
    Ruft eine spezifische Umfrage und deren Elemente aus der Datenbank ab.
    """
    print(f"Rufe Umfrage mit ID {survey_id} ab...")
    # Query, um die Umfrage und ihre Elemente zu laden
    # select(models.Survey).options(selectinload(models.Survey.elements)) lädt Elemente effizient mit
    # Braucht aber Anpassung im Schema oder man macht separate Abfragen
    result = await db.execute(
        select(models.Survey).where(models.Survey.id == survey_id)
    )
    survey = result.scalar_one_or_none()

    if survey is None:
        raise HTTPException(status_code=404, detail="Umfrage nicht gefunden")

    # Lade die Elemente separat (einfacher für den Anfang)
    result_elements = await db.execute(
        select(models.SurveyElement)
        .where(models.SurveyElement.survey_id == survey_id)
        .order_by(models.SurveyElement.page, models.SurveyElement.ordering)  # Sortieren
    )
    elements = result_elements.scalars().all()

    # Baue die Antwort zusammen (manuell, da Pydantic verschachtelt ist)
    # Konvertiere SQLAlchemy-Objekte zu Pydantic-Schemas
    response_elements = [
        schemas.SurveyElementResponse.model_validate(el) for el in elements
    ]

    # Baue das finale SurveyResponse-Objekt
    survey_response_data = schemas.SurveySchema.model_validate(survey).model_dump()
    survey_response_data["questions"] = response_elements  # Füge Elemente hinzu
    survey_response_data["config"] = survey.config or {}  # Füge Config hinzu

    return schemas.SurveyResponse(**survey_response_data)


# --- Starten der Anwendung (wie zuvor) ---
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
