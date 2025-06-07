import os
import uuid
import shutil
import csv
import io
import json
import re
import html
from pathlib import Path
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    UploadFile,
    File,
    status,
    BackgroundTasks,
    Header,
)
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func  # Für DateTime Default
from sqlalchemy.orm import selectinload
from sqlalchemy import delete, update

from openai import AsyncOpenAI

from . import models
from . import schemas
from .database import get_db_session, create_db_and_tables, engine, AsyncSessionFactory


# --- Admin Konfiguration ---
# Beispiel für .env:
# ADMIN_USERNAME="admin"
# ADMIN_PASSWORD="password"
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "secret")
EXPECTED_ADMIN_TOKEN = f"static-admin-token-for-{ADMIN_USERNAME}"


# --- Konfiguration ---
PROJECT_ROOT_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = PROJECT_ROOT_DIR / "uploads/images"
STATIC_FILES_ROUTE = "/static_images"  # Dieser Pfad bleibt relativ zur Domain
BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000")

# Upload-Verzeichnis direkt beim Import erstellen, vor app.mount
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
print(f"Upload-Verzeichnis (beim Import) sichergestellt: {UPLOAD_DIR.resolve()}")

# OpenAI API Key laden
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print(
        "WARNUNG: OPENAI_API_KEY nicht in .env gefunden. LLM-Funktionalität wird nicht verfügbar sein."
    )
openai_client = None
if OPENAI_API_KEY:
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)


# --- Lifecycle Events (unverändert) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Anwendung startet...")
    await create_db_and_tables()
    yield
    print("Anwendung fährt herunter...")
    await engine.dispose()


# --- FastAPI App Instanz ---
app = FastAPI(title="Survey Tool Backend", lifespan=lifespan)

# --- CORS Middleware (WICHTIG für Frontend-Zugriff) ---
fallback_origins = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "https://survey-tool-vue3.vercel.app",
]

env_origins = os.getenv("BACKEND_ALLOWED_ORIGINS")
origins = []

if env_origins:
    origins = [origin.strip() for origin in env_origins.split(",")]
    print("CORS: Erlaubte Origins aus Umgebungsvariablen:", origins)
else:
    origins = fallback_origins
    print("CORS: Es werden die Fallback-Origins verwendet:", fallback_origins)
if not origins:
    origins = fallback_origins
    print(
        "CORS: Keine Origins in Umgebungsvariablen gefunden, Fallback-Origins werden verwendet."
    )

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


# --- Dependency-Funktion zur Admin-Token-Verifizierung ---
async def verify_admin_token(authorization: Optional[str] = Header(None)):
    """
    Überprüft das Admin-Token im Authorization-Header.
    Für diese Phase wird ein einfaches, statisches Token erwartet.
    """
    if authorization is None:
        print("Admin-Zugriff verweigert: Kein Authorization-Header.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nicht autorisiert: Token erforderlich.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split()
    # Erwartetes Format: "Bearer <token>"
    if len(parts) != 2 or parts[0].lower() != "bearer":
        print(
            f"Admin-Zugriff verweigert: Ungültiges Token-Format im Header: {authorization}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges Token-Format. Erwartet: 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]
    if token == EXPECTED_ADMIN_TOKEN:
        # Token ist gültig (für diesen einfachen Fall)
        print(f"Admin-Token verifiziert für Benutzer: {ADMIN_USERNAME}")
        return {
            "username": ADMIN_USERNAME,
            "token_status": "verified",
        }  # Gibt ein einfaches Objekt zurück
    else:
        print(f"Admin-Zugriff verweigert: Ungültiges Token empfangen: {token}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges oder abgelaufenes Token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# --- API Endpunkte ---
@app.get("/")
async def read_root():
    return {"message": "Willkommen zum Survey Tool Backend!"}


# --- Admin Login Endpunkt ---
@app.post("/api/admin/login", response_model=schemas.Token)
async def login_for_admin_access_token(admin_credentials: schemas.AdminLoginRequest):
    if (
        admin_credentials.username == ADMIN_USERNAME
        and admin_credentials.password == ADMIN_PASSWORD
    ):
        access_token = EXPECTED_ADMIN_TOKEN  # Verwende das definierte erwartete Token
        print(f"Admin '{admin_credentials.username}' erfolgreich eingeloggt.")
        return {"access_token": access_token, "token_type": "bearer"}
    else:
        print(
            f"Fehlgeschlagener Admin-Login für Benutzer: '{admin_credentials.username}'"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger Benutzername oder Passwort",
            headers={"WWW-Authenticate": "Bearer"},
        )


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
        relative_url_path = (
            f"{STATIC_FILES_ROUTE}/{unique_filename}"  # Pfad für Frontend
        )

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
@app.post(
    "/api/results",
    response_model=schemas.SurveyResultResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_survey_results(
    result_data: schemas.SurveyResultCreate, db: AsyncSession = Depends(get_db_session)
):
    """
    Speichert die Ergebnisse einer Umfrageteilnahme, inklusive der Antworten
    und der LLM-Chat-Verläufe pro Frage.
    """
    survey_id_extracted = None
    # Ermittlung der survey_id
    if result_data.answers:
        first_answer_element_id_str = next(iter(result_data.answers))
        first_answer_element_id = int(first_answer_element_id_str)
        element_stmt = await db.execute(
            select(models.SurveyElement.survey_id).where(
                models.SurveyElement.id == first_answer_element_id
            )
        )
        survey_id_from_element = element_stmt.scalar_one_or_none()
        if survey_id_from_element:
            survey_id_extracted = survey_id_from_element
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Survey für Element ID {first_answer_element_id_str} nicht gefunden.",
            )
    else:
        raise HTTPException(
            status_code=400, detail="Keine Antworten zum Speichern vorhanden."
        )

    survey = await db.get(models.Survey, survey_id_extracted)
    if not survey:
        raise HTTPException(
            status_code=404,
            detail=f"Survey with ID {survey_id_extracted} not found, cannot save results.",
        )

    participant_start_time_to_use = result_data.participant_start_time or func.now()

    # 1. Erstelle den Teilnehmer-Eintrag
    new_participant = models.SurveyParticipant(
        survey_id=survey_id_extracted,
        prolific_pid=result_data.prolific_pid if survey.prolific_enabled else None,
        study_id=result_data.study_id if survey.prolific_enabled else None,
        session_id=result_data.session_id if survey.prolific_enabled else None,
        is_test_run=result_data.is_test_run if result_data.is_test_run else False,
        consent_given=result_data.consent_given,
        start_time=participant_start_time_to_use,
        end_time=func.now(),  # Aktuelle Zeit als Endzeit
        completed=True,  # Annahme: Wenn Ergebnisse gesendet werden, ist die Umfrage abgeschlossen
        page_durations_log=result_data.page_durations_ms
        if result_data.page_durations_ms
        else None,
    )
    db.add(new_participant)
    await db.flush()  # Um die ID des neuen Teilnehmers zu erhalten
    await db.refresh(new_participant)
    print(f"Teilnehmer erstellt mit ID: {new_participant.id}")

    # 2. Speichere die einzelnen Antworten und zugehörige Chat-Verläufe
    responses_to_add = []
    for survey_element_id_str, answer_value in result_data.answers.items():
        try:
            survey_element_id = int(
                survey_element_id_str
            )  # Konvertiere ID-String zu Integer
        except ValueError:
            print(
                f"WARNUNG: Ungültige survey_element_id '{survey_element_id_str}' in answers übersprungen."
            )
            continue

        # Hole den zugehörigen Chat-Verlauf, falls vorhanden
        chat_history_for_element = None
        if (
            result_data.llm_chat_histories
            and survey_element_id_str in result_data.llm_chat_histories
        ):
            chat_history_for_element = [
                chat_msg.model_dump()
                for chat_msg in result_data.llm_chat_histories[survey_element_id_str]
            ]
            print(
                f"  Chat-Verlauf für Element {survey_element_id_str} gefunden ({len(chat_history_for_element)} Nachrichten)."
            )

        paste_count_for_element = (
            result_data.paste_counts.get(survey_element_id_str, 0)
            if result_data.paste_counts
            else 0
        )
        focus_lost_count_for_element = (
            result_data.focus_lost_counts.get(survey_element_id_str, 0)
            if result_data.focus_lost_counts
            else 0
        )
        display_info = (
            result_data.element_display_info.get(survey_element_id_str)
            if result_data.element_display_info
            else None
        )
        displayed_page_val = display_info.get("page") if display_info else None
        displayed_ordering_val = display_info.get("ordering") if display_info else None

        new_response = models.Response(
            participant_id=new_participant.id,
            survey_element_id=survey_element_id,
            response_value=answer_value,  # Antwortwert direkt speichern (kann str, list, int etc. sein)
            llm_chat_history=chat_history_for_element,  # Füge den Chat-Verlauf hinzu (oder None)
            paste_count=paste_count_for_element,
            focus_lost_count=focus_lost_count_for_element,
            displayed_page=displayed_page_val,
            displayed_ordering=displayed_ordering_val,
        )
        responses_to_add.append(new_response)

    if responses_to_add:
        db.add_all(responses_to_add)
        print(f"{len(responses_to_add)} Antworten zur Datenbank hinzugefügt.")
    else:
        print("Keine gültigen Antworten zum Speichern gefunden.")

    # Commit der Transaktion erfolgt durch die `get_db_session` Dependency
    return schemas.SurveyResultResponse(participant_id=new_participant.id)


# --- Umfrage-Definitions-Endpunkte ---
# Endpunkt zum Auflisten aller Umfragen
@app.get("/api/surveys", response_model=List[schemas.SurveyListItem])
async def list_surveys(db: AsyncSession = Depends(get_db_session)):
    """Gibt eine Liste aller Umfragen mit Basisinformationen zurück."""
    result = await db.execute(
        select(models.Survey).order_by(models.Survey.updated_at.desc())
    )
    surveys = result.scalars().all()

    # Füge die Anzahl der Elemente zu jeder Umfrage hinzu (effizienter wäre eine Subquery oder Join)
    survey_list_items = []
    for survey in surveys:
        count_result = await db.execute(
            select(func.count(models.SurveyElement.id)).where(
                models.SurveyElement.survey_id == survey.id
            )
        )
        element_count = count_result.scalar_one()
        survey_list_items.append(
            schemas.SurveyListItem(
                id=survey.id,
                title=survey.title,
                description=survey.description,
                created_at=survey.created_at,
                updated_at=survey.updated_at,
                element_count=element_count,
                prolific_enabled=survey.prolific_enabled,
                enable_advanced_tracking=getattr(
                    survey, "enable_advanced_tracking", False
                ),
            )
        )
    return survey_list_items


@app.post("/api/surveys", response_model=schemas.SurveyCreateResponse, status_code=201)
async def create_survey(
    survey_in: schemas.SurveyCreate,  # Nimmt Daten gemäß SurveyCreate Schema entgegen
    background_tasks: BackgroundTasks,  # Für Hintergrund-Tasks
    db: AsyncSession = Depends(get_db_session),
    admin_user: dict = Depends(verify_admin_token),
):
    """
    Erstellt eine neue Umfrage und deren Elemente in der Datenbank.
    """
    print(
        f"Admin '{admin_user['username']}' erstellt eine neue Umfrage: '{survey_in.title}'"
    )

    # 1. Erstelle den Haupteintrag für die Umfrage
    new_survey = models.Survey(
        title=survey_in.title,
        description=survey_in.survey_description,
        config=survey_in.config.model_dump(),
        prolific_enabled=survey_in.prolific_enabled,
        prolific_completion_url=survey_in.prolific_completion_url,
        enable_advanced_tracking=survey_in.enable_advanced_tracking,
        track_copy_paste=survey_in.track_copy_paste,
        track_tab_focus=survey_in.track_tab_focus,
        track_page_duration=survey_in.track_page_duration,
        display_time_spent=survey_in.display_time_spent,
        enable_max_duration=survey_in.enable_max_duration,
        max_duration_minutes=survey_in.max_duration_minutes,
        max_duration_warning_minutes=survey_in.max_duration_warning_minutes,
    )
    db.add(new_survey)
    await db.flush()  # Spüle, um die ID der neuen Umfrage zu bekommen
    await db.refresh(new_survey)
    print(f"Survey erstellt mit ID: {new_survey.id}")

    # 2. Erstelle die Elemente (Fragen etc.) und verknüpfe sie
    elements_to_add = []
    for element_data in survey_in.questions:
        element_dict = element_data.model_dump()
        element_dict["survey_id"] = new_survey.id
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
        select(models.Survey)
        .options(selectinload(models.Survey.elements))
        .where(models.Survey.id == survey_id)
    )
    survey = result.scalar_one_or_none()

    if survey is None:
        raise HTTPException(status_code=404, detail="Umfrage nicht gefunden")

    sorted_elements = sorted(survey.elements, key=lambda el: (el.page, el.ordering))

    response_elements = [
        schemas.SurveyElementResponse.model_validate(el) for el in sorted_elements
    ]

    return schemas.SurveyResponse(
        id=survey.id,
        title=survey.title,
        survey_description=survey.description,
        config=survey.config or {},
        created_at=survey.created_at,
        questions=response_elements,
        prolific_enabled=getattr(survey, "prolific_enabled", False),
        prolific_completion_url=getattr(survey, "prolific_completion_url", None),
        enable_advanced_tracking=getattr(survey, "enable_advanced_tracking", False),
        track_copy_paste=getattr(survey, "track_copy_paste", False),
        track_tab_focus=getattr(survey, "track_tab_focus", False),
        track_page_duration=getattr(survey, "track_page_duration", False),
        display_time_spent=getattr(survey, "display_time_spent", False),
        enable_max_duration=getattr(survey, "enable_max_duration", False),
        max_duration_minutes=getattr(survey, "max_duration_minutes", None),
        max_duration_warning_minutes=getattr(
            survey, "max_duration_warning_minutes", None
        ),
        updated_at=survey.updated_at,
    )


# Endpunkt zum Aktualisieren einer bestehenden Umfrage
@app.put("/api/surveys/{survey_id}", response_model=schemas.SurveyUpdateResponse)
async def update_survey(
    survey_id: int,
    survey_in: schemas.SurveyCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session),
    admin_user: dict = Depends(verify_admin_token),
):
    print(f"Admin '{admin_user['username']}' aktualisiert Umfrage ID: {survey_id}")

    # 1. Umfrage aus DB laden
    result = await db.execute(
        select(models.Survey)
        .options(
            selectinload(models.Survey.elements),
            selectinload(models.Survey.participants).selectinload(
                models.SurveyParticipant.responses
            ),
        )  # Lade Teilnehmer und deren Antworten
        .where(models.Survey.id == survey_id)
    )
    db_survey = result.scalar_one_or_none()
    if db_survey is None:
        raise HTTPException(status_code=404, detail="Umfrage nicht gefunden")

    # 2. Prüfen, ob Antworten existieren und ggf. löschen
    if db_survey.participants:
        print(
            f"WARNUNG: Umfrage {survey_id} hat {len(db_survey.participants)} Teilnehmer. Zugehörige Antworten und Teilnehmerdaten werden gelöscht."
        )
        for participant in db_survey.participants:
            # Lösche alle Antworten dieses Teilnehmers
            if participant.responses:
                for response in participant.responses:  # Notwendig, wenn cascade nicht perfekt greift oder für explizite Logik
                    await db.delete(response)
                await db.flush()  # Stelle sicher, dass Antworten gelöscht sind, bevor Teilnehmer gelöscht wird
            await db.delete(participant)
        await db.flush()  # Stelle sicher, dass Teilnehmer gelöscht sind
        # Nachdem die Teilnehmer gelöscht wurden, sollte die participants-Liste der Umfrage leer sein
        db_survey.participants.clear()  # Explizit leeren, um ORM-State zu aktualisieren
        print(f"Alle Teilnehmer und deren Antworten für Umfrage {survey_id} gelöscht.")

    # 3. Felder der Umfrage aktualisieren
    db_survey.title = survey_in.title
    db_survey.description = survey_in.survey_description
    db_survey.config = survey_in.config.model_dump()
    db_survey.prolific_enabled = survey_in.prolific_enabled
    db_survey.prolific_completion_url = survey_in.prolific_completion_url
    db_survey.enable_advanced_tracking = survey_in.enable_advanced_tracking
    db_survey.track_copy_paste = survey_in.track_copy_paste
    db_survey.track_tab_focus = survey_in.track_tab_focus
    db_survey.track_page_duration = survey_in.track_page_duration
    db_survey.display_time_spent = survey_in.display_time_spent
    db_survey.enable_max_duration = survey_in.enable_max_duration
    db_survey.max_duration_minutes = survey_in.max_duration_minutes
    db_survey.max_duration_warning_minutes = survey_in.max_duration_warning_minutes
    db_survey.updated_at = func.now()  # Aktualisiere Zeitstempel

    # 4. Alte Elemente löschen (SQLAlchemy ORM kümmert sich darum, wenn die Beziehung korrekt konfiguriert ist)
    # Es ist sicherer, sie explizit zu löschen, um ORM-Überraschungen zu vermeiden.
    if db_survey.elements:
        print(
            f"Lösche {len(db_survey.elements)} alte Elemente für Survey ID {survey_id}"
        )
        for (
            old_element
        ) in db_survey.elements:  # Iteriere über eine Kopie oder lösche rückwärts
            await db.delete(old_element)
        await db.flush()  # Wende Löschungen an
        db_survey.elements.clear()  # Leere die Kollektion im ORM
        print(f"Alte Elemente für Survey ID {survey_id} gelöscht.")

    # 5. Neue Elemente erstellen und hinzufügen
    elements_to_add = []
    for element_data in survey_in.questions:
        element_dict = element_data.model_dump(exclude_unset=True)
        if (
            "id" in element_dict
        ):  # Entferne Frontend-ID, da DB neue generiert oder Konflikte vermeidet
            del element_dict["id"]
        element_dict["max_duration_seconds"] = element_data.max_duration_seconds
        element_dict["survey_id"] = survey_id  # Verknüpfe mit der aktuellen Umfrage
        new_element = models.SurveyElement(**element_dict)
        elements_to_add.append(new_element)

    if elements_to_add:
        db_survey.elements.extend(elements_to_add)  # Füge neue Elemente hinzu
        print(f"{len(elements_to_add)} neue Survey-Elemente hinzugefügt.")

    await db.commit()  # Committe alle Änderungen (Umfrage-Update, Element-Löschung/Hinzufügung, Teilnehmer/Antwort-Löschung)
    await db.refresh(db_survey)  # Lade die Umfrage neu, um den aktuellen Stand zu haben

    background_tasks.add_task(perform_image_cleanup)
    return schemas.SurveyUpdateResponse(survey_id=survey_id)


# Endpunkt zum Löschen einer Umfrage
@app.delete("/api/surveys/{survey_id}", response_model=schemas.SurveyDeleteResponse)
async def delete_survey(
    survey_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session),
    admin_user: dict = Depends(verify_admin_token),
):
    print(f"Admin '{admin_user['username']}' löscht Umfrage ID: {survey_id}")

    # Lade die Umfrage mit ihren Teilnehmern, deren Antworten und den Elementen
    result = await db.execute(
        select(models.Survey)
        .options(
            selectinload(models.Survey.participants).selectinload(
                models.SurveyParticipant.responses
            ),
            selectinload(models.Survey.elements),
        )
        .where(models.Survey.id == survey_id)
    )
    db_survey = result.scalar_one_or_none()

    if db_survey is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Umfrage nicht gefunden"
        )

    if db_survey.participants:
        print(
            f"WARNUNG: Umfrage {survey_id} hat {len(db_survey.participants)} Teilnehmer. Zugehörige Antworten und Teilnehmerdaten werden ebenfalls gelöscht."
        )
        # Explizit Responses löschen, bevor Elemente oder Teilnehmer gelöscht werden,
        # um ForeignKey-Konflikte mit survey_elements zu vermeiden.
        participant_ids = [p.id for p in db_survey.participants]
        if participant_ids:
            # Lösche alle Responses, die zu den Teilnehmern dieser Umfrage gehören
            stmt_delete_responses = delete(models.Response).where(
                models.Response.participant_id.in_(participant_ids)
            )
            await db.execute(stmt_delete_responses)
            print(
                f"Alle Responses für Teilnehmer der Umfrage {survey_id} zum Löschen markiert."
            )
            await (
                db.flush()
            )  # Sicherstellen, dass Responses vor dem Rest gelöscht werden

        for participant in db_survey.participants:
            await db.delete(participant)
        await db.flush()  # Teilnehmer löschen
        print(f"Alle Teilnehmer für Umfrage {survey_id} gelöscht.")
        db_survey.participants.clear()  # ORM-State aktualisieren

    if db_survey.elements:
        print(f"Lösche {len(db_survey.elements)} Elemente für Survey ID {survey_id}")
        element_ids = [el.id for el in db_survey.elements]

        # ### Breche alle Self-Referencing Foreign Keys ###
        # Setze `references_element_id` auf NULL für alle Elemente dieser Umfrage,
        # bevor wir versuchen, sie zu löschen.
        stmt_break_references = (
            update(models.SurveyElement)
            .where(models.SurveyElement.id.in_(element_ids))
            .values(references_element_id=None)
        )
        await db.execute(stmt_break_references)
        print("Self-referencing foreign keys für Elemente der Umfrage entfernt.")
        # ### ENDE NEUER SCHRITT ###

        # Jetzt können alle Elemente sicher gelöscht werden
        stmt_delete_elements = delete(models.SurveyElement).where(
            models.SurveyElement.id.in_(element_ids)
        )
        await db.execute(stmt_delete_elements)
        print(f"Alle Elemente für Umfrage {survey_id} gelöscht.")

        await db.delete(db_survey)
        print(f"Umfrage mit ID {survey_id} zum Löschen markiert.")

        print(
            f"Umfrage mit ID {survey_id} und alle zugehörigen Daten erfolgreich aus der DB gelöscht."
        )

    background_tasks.add_task(perform_image_cleanup)
    return schemas.SurveyDeleteResponse(
        survey_id=survey_id, message=f"Umfrage {survey_id} erfolgreich gelöscht."
    )


# --- ENDPUNKT FÜR ADMIN ERGEBNISANSICHT ---
@app.get(
    "/api/admin/surveys/{survey_id}/results",
    response_model=schemas.SurveyResultsAdminResponse,
)
async def get_survey_results_for_admin(
    survey_id: int,
    db: AsyncSession = Depends(get_db_session),
    admin_user: dict = Depends(verify_admin_token),
):
    print(
        f"Admin '{admin_user['username']}' fordert Ergebnisse für Survey ID {survey_id} an."
    )

    survey_stmt = select(models.Survey).where(models.Survey.id == survey_id)
    survey_result = await db.execute(survey_stmt)
    survey = survey_result.scalar_one_or_none()

    if not survey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Umfrage nicht gefunden"
        )

    # Lade alle SurveyElements für diese Umfrage einmal, um sie später zuzuordnen
    elements_stmt = select(models.SurveyElement).where(
        models.SurveyElement.survey_id == survey_id
    )
    elements_result = await db.execute(elements_stmt)
    survey_elements_list = elements_result.scalars().all()
    elements_map = {el.id: el for el in survey_elements_list}

    participants_stmt = (
        select(models.SurveyParticipant)
        .where(models.SurveyParticipant.survey_id == survey_id)
        .options(selectinload(models.SurveyParticipant.responses))
        .order_by(models.SurveyParticipant.start_time.desc())
    )
    participants_result = await db.execute(participants_stmt)
    db_participants = participants_result.scalars().all()

    participant_details_list: List[schemas.ParticipantResultDetail] = []
    for p in db_participants:
        answer_details_list: List[schemas.AnswerDetail] = []
        for resp in p.responses:
            # Finde das zugehörige SurveyElement aus der vorgeladenen Map
            survey_element = elements_map.get(resp.survey_element_id)

            answer_details_list.append(
                schemas.AnswerDetail(
                    id=resp.id,
                    survey_element_id=resp.survey_element_id,
                    element_type=survey_element.element_type
                    if survey_element
                    else "N/A",
                    question_type=survey_element.question_type
                    if survey_element
                    else None,
                    question_text=survey_element.question_text
                    if survey_element
                    else "Fragetext nicht gefunden",
                    task_identifier=survey_element.task_identifier
                    if survey_element
                    else None,
                    references_element_id=survey_element.references_element_id
                    if survey_element
                    else None,
                    randomization_group=survey_element.randomization_group
                    if survey_element
                    else None,
                    response_value=resp.response_value,
                    llm_chat_history=resp.llm_chat_history,
                    paste_count=resp.paste_count,
                    created_at=resp.created_at,
                    focus_lost_count=resp.focus_lost_count,
                    displayed_page=resp.displayed_page,
                    displayed_ordering=resp.displayed_ordering,
                )
            )

        participant_details_list.append(
            schemas.ParticipantResultDetail(
                participant_id=p.id,
                prolific_pid=p.prolific_pid,
                study_id=p.study_id,
                session_id=p.session_id,
                start_time=p.start_time,
                end_time=p.end_time,
                consent_given=p.consent_given,
                completed=p.completed,
                is_test_run=p.is_test_run,
                responses=answer_details_list,
                page_durations_log=p.page_durations_log,
            )
        )

    return schemas.SurveyResultsAdminResponse(
        survey_id=survey.id,
        title=survey.title,
        total_participants=len(db_participants),
        participants=participant_details_list,
    )


# --- Endpunkt für LLM-Textgenerierung ---
@app.post("/api/llm/generate-text", response_model=schemas.LLMResponse)
async def generate_llm_text(request_data: schemas.LLMRequest):
    """
    Nimmt einen Fragetext und eine Nutzereingabe entgegen,
    generiert Text mit OpenAI und gibt ihn zurück.
    """
    if not openai_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenAI API-Schlüssel nicht konfiguriert. LLM-Funktion nicht verfügbar.",
        )

    print(
        f"LLM-Chat-Anfrage: Frage='{request_data.question_text[:50]}...', History-Länge='{len(request_data.chat_history)}'"
    )

    # Standard-Prompt-Struktur
    # Der Nutzer steuert die KI durch seine `user_input`, die hier als Aufforderung dient.
    system_prompt = (
        "Based on the following chat history, formulate or complete the user's answer. "
        "Respond precisely and relevantly. Output your answer in the user's input language."
    )

    messages_for_openai = [{"role": "system", "content": system_prompt}]

    # Interaktionslimit: Nimm die letzten N Nachrichten
    MAX_CHAT_HISTORY_PAIRS = 10  # 10 User + 10 Assistant = 20 Nachrichten

    start_index = max(0, len(request_data.chat_history) - (MAX_CHAT_HISTORY_PAIRS * 2))
    limited_chat_history = request_data.chat_history[start_index:]

    for msg in limited_chat_history:
        messages_for_openai.append({"role": msg.role, "content": msg.content})

    try:
        openai_model = os.getenv("OPENAI_MODEL", "gpt-4.1-nano")
        print(
            f"Sende an OpenAI ({openai_model}) mit {len(messages_for_openai)} Nachrichten..."
        )

        chat_completion = await openai_client.chat.completions.create(
            messages=messages_for_openai,
            model=openai_model,
        )
        generated_text = chat_completion.choices[0].message.content
        model_used = chat_completion.model

        # Token-Nutzung loggen
        if chat_completion.usage:
            print(
                f"OpenAI Token-Nutzung: Prompt Tokens={chat_completion.usage.prompt_tokens}, "
                f"Completion Tokens={chat_completion.usage.completion_tokens}, "
                f"Total Tokens={chat_completion.usage.total_tokens}"
            )
        else:
            print("OpenAI Token-Nutzung: Nicht in Antwort enthalten.")

        print(f"LLM-Antwort von {model_used}: '{generated_text[:100]}...'")
        return schemas.LLMResponse(
            generated_text=generated_text.strip(), model_used=model_used
        )

    except Exception as e:
        print(f"Fehler bei der OpenAI API-Anfrage: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler bei der Kommunikation mit dem LLM: {str(e)}",
        )


@app.get(
    "/api/admin/export/all_data/flat",
    response_model=schemas.AllDataFlatExport,
    dependencies=[Depends(verify_admin_token)],
)
async def export_all_data_flat(db: AsyncSession = Depends(get_db_session)):
    """Exportiert alle relevanten Daten aus der Datenbank in einer flachen JSON-Struktur."""
    print("Admin exportiert alle Daten (flaches Format).")

    surveys_q = await db.execute(select(models.Survey))
    surveys = [
        schemas.SurveyExport.model_validate(s) for s in surveys_q.scalars().all()
    ]

    elements_q = await db.execute(select(models.SurveyElement))
    survey_elements = [
        schemas.SurveyElementExport.model_validate(el)
        for el in elements_q.scalars().all()
    ]

    participants_q = await db.execute(select(models.SurveyParticipant))
    survey_participants = [
        schemas.SurveyParticipantExport.model_validate(p)
        for p in participants_q.scalars().all()
    ]

    responses_q = await db.execute(select(models.Response))
    responses = [
        schemas.ResponseExport.model_validate(r) for r in responses_q.scalars().all()
    ]

    return schemas.AllDataFlatExport(
        surveys=surveys,
        survey_elements=survey_elements,
        survey_participants=survey_participants,
        responses=responses,
    )


@app.get(
    "/api/admin/export/all_data/nested",
    response_model=schemas.AllDataNestedExport,
    dependencies=[Depends(verify_admin_token)],
)
async def export_all_data_nested(db: AsyncSession = Depends(get_db_session)):
    """Exportiert alle Umfragen mit ihren Elementen und Teilnehmerergebnissen (verschachtelt)."""
    print("Admin exportiert alle Daten (verschachteltes Format).")

    def map_answer_detail(resp_obj, survey_element_for_resp):
        return schemas.AnswerDetail(
            id=resp_obj.id,
            survey_element_id=resp_obj.survey_element_id,
            element_type=survey_element_for_resp.element_type
            if survey_element_for_resp
            else "N/A",
            question_type=survey_element_for_resp.question_type
            if survey_element_for_resp
            else None,
            question_text=survey_element_for_resp.question_text
            if survey_element_for_resp
            else "Fragetext nicht gefunden",
            task_identifier=survey_element_for_resp.task_identifier
            if survey_element_for_resp
            else None,
            references_element_id=survey_element_for_resp.references_element_id
            if survey_element_for_resp
            else None,
            response_value=resp_obj.response_value,
            llm_chat_history=resp_obj.llm_chat_history,
            paste_count=resp_obj.paste_count,
            focus_lost_count=resp_obj.focus_lost_count,
            created_at=resp_obj.created_at,
            displayed_page=getattr(resp_obj, "displayed_page", None),
            displayed_ordering=getattr(resp_obj, "displayed_ordering", None),
        )

    def map_participant_detail(p_obj, elements_map):
        answer_details_list: List[schemas.AnswerDetail] = [
            map_answer_detail(resp_obj, elements_map.get(resp_obj.survey_element_id))
            for resp_obj in p_obj.responses
        ]
        return schemas.ParticipantResultDetail(
            participant_id=p_obj.id,
            prolific_pid=p_obj.prolific_pid,
            study_id=p_obj.study_id,
            session_id=p_obj.session_id,
            start_time=p_obj.start_time,
            end_time=p_obj.end_time,
            consent_given=p_obj.consent_given,
            completed=p_obj.completed,
            is_test_run=p_obj.is_test_run,
            responses=answer_details_list,
            page_durations_log=p_obj.page_durations_log,
        )

    # Lade Umfragen mit allen zugehörigen Daten
    stmt = (
        select(models.Survey)
        .options(
            selectinload(models.Survey.elements),
            selectinload(models.Survey.participants).options(
                selectinload(models.SurveyParticipant.responses)
            ),
        )
        .order_by(models.Survey.id)
    )
    result = await db.execute(stmt)
    db_surveys = result.scalars().unique().all()

    exported_surveys: List[schemas.SurveyFullNestedExport] = []
    for survey_obj in db_surveys:
        elements_map = {el.id: el for el in survey_obj.elements}
        participant_details_list: List[schemas.ParticipantResultDetail] = [
            map_participant_detail(p_obj, elements_map)
            for p_obj in survey_obj.participants
        ]
        survey_elements_response = [
            schemas.SurveyElementResponse.model_validate(el)
            for el in survey_obj.elements
        ]
        exported_survey = schemas.SurveyFullNestedExport(
            id=survey_obj.id,
            title=survey_obj.title,
            survey_description=survey_obj.description,
            config=survey_obj.config,
            created_at=survey_obj.created_at,
            updated_at=survey_obj.updated_at,
            questions=survey_elements_response,
            prolific_enabled=survey_obj.prolific_enabled,
            prolific_completion_url=survey_obj.prolific_completion_url,
            enable_advanced_tracking=survey_obj.enable_advanced_tracking,
            track_copy_paste=survey_obj.track_copy_paste,
            track_tab_focus=survey_obj.track_tab_focus,
            track_page_duration=survey_obj.track_page_duration,
            display_time_spent=survey_obj.display_time_spent,
            enable_max_duration=survey_obj.enable_max_duration,
            max_duration_minutes=survey_obj.max_duration_minutes,
            max_duration_warning_minutes=survey_obj.max_duration_warning_minutes,
            participants_results=participant_details_list,
        )
        exported_surveys.append(exported_survey)

    return schemas.AllDataNestedExport(surveys=exported_surveys)


# Hilfsfunktion zum Entfernen von HTML-Tags und Dekodieren von Entitäten
def strip_html_and_decode_entities(html_string: Optional[str]) -> Optional[str]:
    if not html_string:
        return None
    # Einfache Regex, um die meisten gängigen Tags zu entfernen
    # Dies ist nicht perfekt für komplexes HTML, aber für unsere Zwecke (strong, em, p, h1-6, br) ausreichend.
    text_without_tags = re.sub(
        r"<[^>]+>", " ", html_string
    )  # Ersetzt Tags durch Leerzeichen
    # Dekodiere HTML-Entitäten wie &auml;, &uuml;, &szlig;, &amp; etc.
    text_decoded = html.unescape(text_without_tags)
    # Mehrfache Leerzeichen durch ein einzelnes ersetzen und führende/folgende Leerzeichen entfernen
    return " ".join(text_decoded.split()).strip()


@app.get(
    "/api/admin/export/survey/{survey_id}/csv",
    response_description="CSV file of survey results",
    dependencies=[
        Depends(verify_admin_token)
    ],  # Stelle sicher, dass verify_admin_token hier referenziert wird
)
async def export_survey_results_to_csv(
    survey_id: int,
    db: AsyncSession = Depends(get_db_session),
    admin_user: dict = Depends(
        verify_admin_token
    ),  # admin_user wird von der Dependency injected
):
    """
    Exports all results for a given survey to a CSV file.
    Includes participant data, their answers, and contextual information for each question.
    """
    print(
        f"Admin '{admin_user.get('username', 'Unknown')}' requested CSV export for survey ID {survey_id}."
    )

    # 1. Fetch Survey details
    survey_stmt = select(models.Survey).where(models.Survey.id == survey_id)
    survey_result = await db.execute(survey_stmt)
    survey = survey_result.scalar_one_or_none()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")

    # 2. Fetch all question elements for this survey to define CSV headers
    elements_stmt = (
        select(models.SurveyElement)
        .where(models.SurveyElement.survey_id == survey_id)
        .order_by(models.SurveyElement.page, models.SurveyElement.ordering)
    )
    elements_result = await db.execute(elements_stmt)
    all_survey_elements = elements_result.scalars().all()  # Alle Elemente für Infos

    question_elements = [
        el for el in all_survey_elements if el.element_type == "question"
    ]

    # 3. Define CSV Headers
    headers = [
        "participant_db_id",
        "survey_id",
        "prolific_pid",
        "study_id",
        "session_id",
        "start_time",
        "end_time",
        "consent_given",
        "completed",
        "is_test_run",
        "page_durations_log_json",
        "total_paste_count_survey",
        "total_focus_lost_count_survey",
        "selected_task_group_condition",  # Platzhalter für spätere komplexere Randomisierung
    ]

    for q_el in question_elements:
        base_q_header = f"q_{q_el.id}"
        headers.extend(
            [
                f"{base_q_header}_text",
                f"{base_q_header}_type",
                f"{base_q_header}_task_identifier",
                f"{base_q_header}_randomization_group",
                f"{base_q_header}_llm_enabled_by_config",
                f"{base_q_header}_response_value_json",
                f"{base_q_header}_displayed_page",
                f"{base_q_header}_displayed_ordering",
                f"{base_q_header}_paste_count",
                f"{base_q_header}_focus_lost_count",
                f"{base_q_header}_llm_chat_history_json",
            ]
        )

    # 4. Fetch all participants and their responses
    participants_stmt = (
        select(models.SurveyParticipant)
        .where(models.SurveyParticipant.survey_id == survey_id)
        .options(selectinload(models.SurveyParticipant.responses))
        .order_by(models.SurveyParticipant.start_time.desc())
    )
    participants_result = await db.execute(participants_stmt)
    db_participants = participants_result.scalars().unique().all()

    # 5. Prepare data for CSV
    output = io.StringIO()
    writer = csv.DictWriter(
        output, fieldnames=headers, extrasaction="ignore", quoting=csv.QUOTE_ALL
    )
    writer.writeheader()

    for p in db_participants:
        row = {
            "participant_db_id": p.id,
            "survey_id": p.survey_id,
            "prolific_pid": p.prolific_pid,
            "study_id": p.study_id,
            "session_id": p.session_id,
            "start_time": p.start_time.isoformat() if p.start_time else None,
            "end_time": p.end_time.isoformat() if p.end_time else None,
            "consent_given": p.consent_given,
            "completed": p.completed,
            "is_test_run": p.is_test_run,
            "page_durations_log_json": json.dumps(p.page_durations_log)
            if p.page_durations_log
            else None,
            "selected_task_group_condition": getattr(p, "selected_task_group_id", None),
        }

        total_paste_survey = 0
        total_focus_lost_survey = 0
        responses_map = {str(resp.survey_element_id): resp for resp in p.responses}

        for q_el in question_elements:
            q_id_str = str(q_el.id)
            base_q_header = f"q_{q_el.id}"
            response_for_q = responses_map.get(q_id_str)

            if response_for_q:
                row[f"{base_q_header}_response_value_json"] = json.dumps(
                    response_for_q.response_value
                )
                row[f"{base_q_header}_displayed_page"] = response_for_q.displayed_page
                row[f"{base_q_header}_displayed_ordering"] = (
                    response_for_q.displayed_ordering
                )
                row[f"{base_q_header}_paste_count"] = response_for_q.paste_count
                row[f"{base_q_header}_focus_lost_count"] = (
                    response_for_q.focus_lost_count
                )
                row[f"{base_q_header}_llm_chat_history_json"] = (
                    json.dumps(response_for_q.llm_chat_history)
                    if response_for_q.llm_chat_history
                    else None
                )

                total_paste_survey += response_for_q.paste_count or 0
                total_focus_lost_survey += response_for_q.focus_lost_count or 0
            else:
                row[f"{base_q_header}_response_value_json"] = None
                row[f"{base_q_header}_displayed_page"] = None
                row[f"{base_q_header}_displayed_ordering"] = None
                row[f"{base_q_header}_paste_count"] = None
                row[f"{base_q_header}_focus_lost_count"] = None
                row[f"{base_q_header}_llm_chat_history_json"] = None

            # Add question element's own metadata
            row[f"{base_q_header}_text"] = strip_html_and_decode_entities(
                q_el.question_text
            )
            row[f"{base_q_header}_type"] = q_el.question_type
            row[f"{base_q_header}_task_identifier"] = q_el.task_identifier
            row[f"{base_q_header}_randomization_group"] = q_el.randomization_group
            row[f"{base_q_header}_llm_enabled_by_config"] = q_el.llm_assistance_enabled

        row["total_paste_count_survey"] = total_paste_survey
        row["total_focus_lost_count_survey"] = total_focus_lost_survey

        writer.writerow(row)

    output.seek(0)

    safe_survey_title = "".join(c if c.isalnum() else "_" for c in survey.title)
    filename = f"survey_{survey_id}_{safe_survey_title}_export_extended.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# --- Starten der Anwendung (wie zuvor) ---

if __name__ == "__main__":
    import uvicorn

    # Lese Host und Port aus Umgebungsvariablen, mit Fallbacks
    APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
    APP_PORT = int(os.getenv("APP_PORT", "8000"))
    RELOAD_APP = os.getenv("RELOAD_APP", "True").lower() == "true"

    uvicorn.run("app.main:app", host=APP_HOST, port=APP_PORT, reload=RELOAD_APP)
