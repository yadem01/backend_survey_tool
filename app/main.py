import os
import uuid  # Für eindeutige Dateinamen
import shutil  # Für Dateioperationen
from pathlib import Path  # Für Pfadoperationen
from typing import List, Optional  # Für Typannotationen
from contextlib import asynccontextmanager

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
from sqlalchemy.orm import selectinload  # Für effizientes Laden von Beziehungen

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
    print("Initialisiere Datenbanktabellen...")
    await create_db_and_tables()
    print("Datenbankinitialisierung abgeschlossen.")
    yield
    print("Anwendung fährt herunter...")
    await engine.dispose()


# --- FastAPI App Instanz ---
app = FastAPI(title="Survey Tool Backend", lifespan=lifespan)

# --- CORS Middleware (WICHTIG für Frontend-Zugriff) ---
origins = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "https://survey-tool-vue3.vercel.app",
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


# --- Admin Login Endpunkt ---
@app.post("/api/admin/login", response_model=schemas.Token)
async def login_for_admin_access_token(admin_credentials: schemas.AdminLoginRequest):
    """
    Authentifiziert einen Admin anhand der übergebenen Zugangsdaten.
    Gibt bei Erfolg ein einfaches Token zurück.
    Momentan werden hartkodierte Zugangsdaten verwendet (aus Umgebungsvariablen geladen).
    """
    # Vergleiche die übergebenen Credentials mit den konfigurierten Admin-Daten
    # In einer echten Anwendung: Passwort-Vergleich mit gehashten Passwörtern aus der DB
    is_correct_username = admin_credentials.username == ADMIN_USERNAME
    is_correct_password = (
        admin_credentials.password == ADMIN_PASSWORD
    )  # Direkter Vergleich nur für Demo!

    if not (is_correct_username and is_correct_password):
        print(
            f"Fehlgeschlagener Admin-Login-Versuch für Benutzer: '{admin_credentials.username}'"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger Benutzername oder Passwort",
            headers={
                "WWW-Authenticate": "Bearer"
            },  # Standard-Header für Token-basierte Auth
        )

    # Erzeuge ein einfaches Token. Für eine echte Anwendung sollte hier ein JWT erstellt werden.
    # Beispiel: access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    # access_token = create_access_token(data={"sub": ADMIN_USERNAME}, expires_delta=access_token_expires)

    # Für diese Phase: Ein statisches oder sehr einfaches "Token"
    # Dieses Token dient im Frontend nur als Indikator, dass der Login erfolgreich war.
    # Es wird serverseitig (noch) nicht für die Autorisierung von Endpunkten validiert.
    access_token = f"static-admin-token-for-{ADMIN_USERNAME}"

    print(f"Admin '{admin_credentials.username}' erfolgreich eingeloggt.")
    return {"access_token": access_token, "token_type": "bearer"}


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
    # print("Empfangene Ergebnisdaten (Auszug):")
    # print(f"  Prolific PID: {result_data.prolific_pid}")
    # print(f"  Consent Given: {result_data.consent_given}")
    # print(f"  Anzahl Antworten: {len(result_data.answers)}")
    # print(
    #     f"  Anzahl Chat-Verläufe: {len(result_data.llm_chat_histories if result_data.llm_chat_histories else [])}"
    # )

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

    participant_start_time_to_use = result_data.participant_start_time or func.now()

    # 1. Erstelle den Teilnehmer-Eintrag
    new_participant = models.SurveyParticipant(
        survey_id=survey_id_extracted,
        prolific_pid=result_data.prolific_pid,
        study_id=result_data.study_id,  # study_id hinzugefügt
        session_id=result_data.session_id,  # session_id hinzugefügt
        consent_given=result_data.consent_given,
        start_time=participant_start_time_to_use,
        end_time=func.now(),  # Aktuelle Zeit als Endzeit
        completed=True,  # Annahme: Wenn Ergebnisse gesendet werden, ist die Umfrage abgeschlossen
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

        new_response = models.Response(
            participant_id=new_participant.id,
            survey_element_id=survey_element_id,
            response_value=answer_value,  # Antwortwert direkt speichern (kann str, list, int etc. sein)
            llm_chat_history=chat_history_for_element,  # Füge den Chat-Verlauf hinzu (oder None)
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
            )
        )
    return survey_list_items


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
        prolific_enabled=survey_in.prolific_enabled,
        prolific_completion_url=survey_in.prolific_completion_url,
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
        survey_title=survey.title,
        survey_description=survey.description,
        config=survey.config or {},  # Stelle sicher, dass config ein Dict ist
        created_at=survey.created_at,
        updated_at=survey.updated_at,
        questions=response_elements,
        prolific_enabled=getattr(survey, "prolific_enabled", False),
        prolific_completion_url=getattr(survey, "prolific_completion_url", None),
    )


# Endpunkt zum Aktualisieren einer bestehenden Umfrage
@app.put("/api/surveys/{survey_id}", response_model=schemas.SurveyUpdateResponse)
async def update_survey(
    survey_id: int,
    survey_in: schemas.SurveyCreate,  # Verwendet das gleiche Schema wie beim Erstellen
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session),
):
    """Aktualisiert eine bestehende Umfrage und deren Elemente."""
    print(f"Aktualisiere Umfrage mit ID {survey_id}...")

    # 1. Umfrage aus DB laden
    result = await db.execute(
        select(models.Survey)
        .options(selectinload(models.Survey.elements))
        .where(models.Survey.id == survey_id)
    )
    db_survey = result.scalar_one_or_none()
    if db_survey is None:
        raise HTTPException(status_code=404, detail="Umfrage nicht gefunden")

    # 2. Felder der Umfrage aktualisieren
    db_survey.title = survey_in.survey_title
    db_survey.description = survey_in.survey_description
    db_survey.config = survey_in.config.model_dump()
    db_survey.updated_at = func.now()  # Aktualisiere Zeitstempel

    # 3. Alte Elemente löschen
    if db_survey.elements:  # Nur wenn Elemente vorhanden sind
        print(
            f"Lösche {len(db_survey.elements)} alte Elemente für Survey ID {survey_id}"
        )
        db_survey.elements.clear()
        await db.flush()

    # 4. Neue Elemente erstellen und hinzufügen
    elements_to_add = []
    for element_data in survey_in.questions:
        element_dict = element_data.model_dump(exclude_unset=True)
        if "id" in element_dict:
            del element_dict["id"]  # Entferne Frontend-ID, da DB neue generiert

        element_dict["survey_id"] = survey_id  # Verwende die bestehende survey_id
        new_element = models.SurveyElement(**element_dict)
        elements_to_add.append(new_element)

    if elements_to_add:
        # Füge neue Elemente zur Collection hinzu (SQLAlchemy kümmert sich um das Hinzufügen zur Session)
        db_survey.elements.extend(elements_to_add)
        print(f"{len(elements_to_add)} neue Survey-Elemente hinzugefügt.")

    # db.add(db_survey) # Markiere die Umfrage als geändert (SQLAlchemy erkennt das oft automatisch)
    # Commit wird durch get_db_session erledigt

    background_tasks.add_task(perform_image_cleanup)
    print(f"Bild-Cleanup-Task für Survey ID {survey_id} im Hintergrund gestartet.")

    return schemas.SurveyUpdateResponse(survey_id=survey_id)


# Endpunkt zum Löschen einer Umfrage
@app.delete("/api/surveys/{survey_id}", response_model=schemas.SurveyDeleteResponse)
async def delete_survey(
    survey_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session),
):
    """Löscht eine spezifische Umfrage und alle zugehörigen Daten."""
    print(f"Versuche Umfrage mit ID {survey_id} zu löschen...")

    # 1. Umfrage aus DB laden, um sicherzustellen, dass sie existiert
    result = await db.execute(
        select(models.Survey).where(models.Survey.id == survey_id)
    )
    db_survey = result.scalar_one_or_none()

    if db_survey is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Umfrage nicht gefunden"
        )

    # 2. Umfrage löschen
    # Durch cascade="all, delete-orphan" in den Models werden SurveyElement,
    # SurveyParticipant und deren Responses automatisch mitgelöscht.
    await db.delete(db_survey)
    # Commit wird durch get_db_session erledigt
    print(f"Umfrage mit ID {survey_id} und zugehörige Daten zum Löschen markiert.")

    # 3. Bild-Cleanup im Hintergrund starten
    # Wichtig: Der Cleanup-Task läuft, nachdem die DB-Transaktion committed wurde.
    # Er wird also Bilder löschen, die zu dieser gerade gelöschten Umfrage gehörten.
    background_tasks.add_task(perform_image_cleanup)
    print(
        f"Bild-Cleanup-Task für gelöschte Survey ID {survey_id} im Hintergrund gestartet."
    )

    return schemas.SurveyDeleteResponse(
        survey_id=survey_id, message=f"Umfrage {survey_id} erfolgreich gelöscht."
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
        f"You are a helpful assistant. The original survey question is: '{request_data.question_text}'. "
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
        print(
            f"Sende an OpenAI (gpt-4o-mini) mit {len(messages_for_openai)} Nachrichten..."
        )
        chat_completion = await openai_client.chat.completions.create(
            messages=messages_for_openai,
            model="gpt-4.1-nano",
            # Weitere Parameter wie temperature, max_tokens etc. könnten hier gesetzt werden
            # temperature=0.7,
            # max_tokens=150
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


# --- Starten der Anwendung (wie zuvor) ---
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
