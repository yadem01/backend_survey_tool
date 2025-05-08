from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any, Union
from datetime import datetime


# Basismodell für eine Antwort (wie sie vom Frontend kommen könnte)
class AnswerBase(BaseModel):
    question_id: int
    value: Union[str, List[str], int, float, bool, None]


# Modell für die gesamten Ergebnisse, die vom Frontend gesendet werden
class SurveyResultCreate(BaseModel):
    prolific_pid: Optional[str] = None
    study_id: Optional[str] = None
    session_id: Optional[str] = None
    consent_given: bool
    answers: Dict[str, Union[str, List[str], int, float, bool, None]]


# Modell für die Antwort nach erfolgreichem Speichern (Beispiel)
class SurveyResultResponse(BaseModel):
    participant_id: int
    message: str = "Ergebnisse erfolgreich gespeichert."


# --- Schemas für Bild-Upload (unverändert) ---
class ImageUploadResponse(BaseModel):
    file_path: str


# --- NEU: Schemas für Umfrage-Definition ---


# Schema für ein einzelnes Element (Frage, Info etc.) beim Erstellen/Empfangen
class SurveyElementCreate(BaseModel):
    question_text: Optional[str] = None
    element_type: str  # Typ des Elements ('info', 'consent', 'question')
    question_type: Optional[str] = None  # Nur wenn element_type='question'
    options: Optional[Any] = None  # Flexibel für JSON
    ordering: int = 0
    page: int = 1
    image_url: Optional[str] = None
    required: bool = False
    paste_disabled: bool = False
    randomization_group: Optional[str] = None
    allow_back_navigation: bool = True

    # Validator, um sicherzustellen, dass question_type gesetzt ist, wenn element_type 'question' ist
    @field_validator("question_type", mode="before")
    @classmethod
    def check_question_type(cls, v, info):
        if info.data.get("element_type") == "question" and v is None:
            raise ValueError(
                'question_type is required when element_type is "question"'
            )
        return v


# Schema für die globale Konfiguration der Umfrage
class SurveyConfigCreate(BaseModel):
    randomize_groups: bool = False
    group_selection: Optional[Dict[str, int]] = {}


# Hauptschema für das Erstellen einer neuen Umfrage (kommt vom Frontend)
class SurveyCreate(BaseModel):
    survey_title: str = Field("Neue Umfrage", min_length=1)
    survey_description: Optional[str] = None
    config: SurveyConfigCreate = Field(
        default_factory=SurveyConfigCreate
    )  # Default verwenden
    questions: List[SurveyElementCreate] = []  # Liste der Elemente


# Schema für die Antwort nach dem Erstellen einer Umfrage
class SurveyCreateResponse(BaseModel):
    survey_id: int
    message: str = "Umfrage erfolgreich erstellt."


# Schema zum Zurückgeben einer vollständigen Umfrage (Beispiel)
class SurveyElementResponse(SurveyElementCreate):  # Erbt von Create
    id: int  # Fügt ID hinzu
    survey_id: int

    class Config:
        from_attributes = True


class SurveyResponse(SurveyCreate):  # Erbt von Create
    id: int  # Fügt ID hinzu
    created_at: datetime
    updated_at: Optional[datetime] = None
    questions: List[
        SurveyElementResponse
    ] = []  # Verwendet Response-Schema für Elemente

    class Config:
        from_attributes = True
