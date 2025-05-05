from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select # Für neuere SQLAlchemy Select-Syntax
from sqlalchemy.sql import func # Für SQL-Funktionen wie now()
import models # Importiere die SQLAlchemy-Modelle
import schemas # Importiere die Pydantic-Schemas
from database import get_db_session, create_db_and_tables, engine # Importiere DB-Helfer
from contextlib import asynccontextmanager

# --- Lifecycle Events für DB-Initialisierung ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code hier wird beim Start ausgeführt
    print("Anwendung startet...")
    # Erstelle DB-Tabellen beim Start (nur wenn sie nicht existieren)
    # In Produktion besser Migrationstools wie Alembic verwenden!
    # await create_db_and_tables()
    yield
    # Code hier wird beim Beenden ausgeführt
    print("Anwendung fährt herunter...")
    await engine.dispose() # Schließe DB-Verbindungspool

# --- FastAPI App Instanz ---
# Füge das Lifespan-Management hinzu
app = FastAPI(title="Survey Tool Backend", lifespan=lifespan)

# --- API Endpunkte ---

# Einfacher Root-Endpunkt zum Testen
@app.get("/")
async def read_root():
    return {"message": "Willkommen zum Survey Tool Backend!"}

# NEU: Endpunkt zum Speichern von Umfrageergebnissen
@app.post("/api/results", response_model=schemas.SurveyResultResponse, status_code=201)
async def save_survey_results(
    result_data: schemas.SurveyResultCreate,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Nimmt die Umfrageergebnisse vom Frontend entgegen und speichert sie.
    (Aktuell: Erstellt Teilnehmer und speichert Antworten)
    """
    print("Empfangene Ergebnisdaten:", result_data.model_dump()) # model_dump() statt dict()

    # TODO: Hier müsste die Logik hin, um die Survey ID zu finden,
    #       falls mehrere Umfragen unterstützt werden.
    #       Fürs Erste nehmen wir an, es gibt nur eine oder die ID ist bekannt.
    survey_id_example = 1 # Beispielhafte Annahme

    # 1. Teilnehmer erstellen oder finden
    # Hier einfache Erstellung, in Realität prüfen, ob Teilnehmer schon existiert (via prolific_pid?)
    new_participant = models.SurveyParticipant(
        survey_id=survey_id_example, # Annahme
        prolific_pid=result_data.prolific_pid,
        consent_given=result_data.consent_given,
        completed=True, # Markieren als abgeschlossen beim Speichern
        end_time=func.now() # Endzeit setzen
        # start_time wird durch server_default gesetzt
    )
    db.add(new_participant)
    await db.flush() # Spüle, um die ID des Teilnehmers zu bekommen
    await db.refresh(new_participant)
    print(f"Teilnehmer erstellt mit ID: {new_participant.id}")

    # 2. Antworten speichern
    responses_to_add = []
    for question_id_str, value in result_data.answers.items():
        try:
            question_id = int(question_id_str) # Konvertiere Key zu Integer
            new_response = models.Response(
                participant_id=new_participant.id,
                survey_element_id=question_id,
                response_value=value # Speichert Wert als JSON
            )
            responses_to_add.append(new_response)
        except ValueError:
            print(f"Warnung: Ungültige Question ID '{question_id_str}' in Antworten übersprungen.")
            continue # Überspringe ungültige IDs

    if responses_to_add:
        db.add_all(responses_to_add)
        print(f"{len(responses_to_add)} Antworten hinzugefügt.")

    # try:
    #     await db.commit() # Committen am Ende (wird durch get_db_session erledigt)
    # except Exception as e:
    #     await db.rollback()
    #     print(f"Fehler beim Speichern: {e}")
    #     raise HTTPException(status_code=500, detail="Fehler beim Speichern der Ergebnisse.")

    return schemas.SurveyResultResponse(participant_id=new_participant.id)