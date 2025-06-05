from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List, Optional, Dict, Any, Union
from datetime import datetime


# Schemas für LLM-Anbindung
class ChatMessage(BaseModel):
    role: str  # "user" oder "assistant"
    content: str


class LLMRequest(BaseModel):
    question_text: str = Field(
        ..., description="Der ursprüngliche Text der Umfragefrage."
    )
    chat_history: List[ChatMessage] = Field(
        default_factory=list, description="Der bisherige Chatverlauf."
    )


class LLMResponse(BaseModel):
    generated_text: str
    model_used: Optional[str] = None


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
    llm_chat_histories: Optional[Dict[str, List[ChatMessage]]] = Field(
        default_factory=dict
    )
    participant_start_time: Optional[datetime] = None

    paste_counts: Optional[Dict[str, int]] = Field(default_factory=dict)
    focus_lost_counts: Optional[Dict[str, int]] = Field(default_factory=dict)
    page_durations_ms: Optional[Dict[str, int]] = Field(default_factory=dict)

    element_display_info: Optional[Dict[str, Dict[str, int]]] = Field(
        default_factory=dict
    )


# Modell für die Antwort nach erfolgreichem Speichern (Beispiel)
class SurveyResultResponse(BaseModel):
    participant_id: int
    message: str = "Ergebnisse erfolgreich gespeichert."


# --- Schemas für Bild-Upload (unverändert) ---
class ImageUploadResponse(BaseModel):
    file_path: str


# --- Schemas für Umfrage-Definition ---


class SurveyElementBase(BaseModel):  # Basis für Element, ohne Validatoren für Create
    question_text: Optional[str] = None
    element_type: str
    question_type: Optional[str] = None
    options: Optional[Any] = None
    ordering: int = 0
    page: int = 1
    image_url: Optional[str] = None
    required: bool = False
    paste_disabled: bool = False
    randomization_group: Optional[str] = None
    allow_back_navigation: bool = True
    llm_assistance_enabled: bool = Field(default=False)
    maxlength: Optional[int] = None
    task_identifier: Optional[str] = Field(default=None)
    references_element_id: Optional[int] = Field(default=None)
    max_duration_seconds: Optional[int] = Field(default=None, ge=0)


class SurveyElementCreate(SurveyElementBase):
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
    group_selection: Optional[Dict[str, int]] = Field(default_factory=dict)


# Hauptschema für das Erstellen einer neuen Umfrage
class SurveyBase(BaseModel):  # Basis für Survey, ohne Validatoren für Create
    title: str
    survey_description: Optional[str] = None
    config: SurveyConfigCreate = Field(default_factory=SurveyConfigCreate)
    prolific_enabled: bool = Field(default=False)
    prolific_completion_url: Optional[str] = None
    enable_advanced_tracking: bool = Field(default=False)
    track_copy_paste: bool = Field(default=False)
    track_tab_focus: bool = Field(default=False)
    track_page_duration: bool = Field(default=False)
    display_time_spent: bool = Field(default=False)
    enable_max_duration: bool = Field(default=False)
    max_duration_minutes: Optional[int] = Field(default=None, ge=0)
    max_duration_warning_minutes: Optional[int] = Field(default=None, ge=0)


class SurveyCreate(SurveyBase):
    title: str = Field("Neue Umfrage", min_length=1)  # Überschreibe für Default
    questions: List[SurveyElementCreate] = []


# Schema für die Antwort nach dem Erstellen einer Umfrage
class SurveyCreateResponse(BaseModel):
    survey_id: int
    message: str = "Umfrage erfolgreich erstellt."


# Schema zum Zurückgeben einer vollständigen Umfrage (Beispiel)
class SurveyElementResponse(SurveyElementCreate):  # Erbt von Create
    id: int
    survey_id: int

    model_config = ConfigDict(from_attributes=True)


class SurveyResponse(SurveyCreate):  # Erbt von Create
    id: int  # Fügt ID hinzu
    created_at: datetime
    updated_at: Optional[datetime] = None
    questions: List[
        SurveyElementResponse
    ] = []  # Verwendet Response-Schema für Elemente

    model_config = ConfigDict(from_attributes=True)


# Schema für einen Listeneintrag einer Umfrage
class SurveyListItem(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    element_count: int
    prolific_enabled: bool = Field(default=False)
    track_copy_paste: bool = Field(default=False)
    track_tab_focus: bool = Field(default=False)
    track_page_duration: bool = Field(default=False)
    display_time_spent: bool = Field(default=False)
    enable_max_duration: bool = Field(default=False)
    max_duration_minutes: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


# Schema für die Antwort beim Aktualisieren einer Umfrage
class SurveyUpdateResponse(BaseModel):
    survey_id: int
    message: str = "Umfrage erfolgreich aktualisiert."


# Schema für die Antwort beim Löschen einer Umfrage
class SurveyDeleteResponse(BaseModel):
    survey_id: int
    message: str = "Umfrage erfolgreich gelöscht."


# --- Schemas für Admin Login ---


class AdminLoginRequest(BaseModel):
    """Schema für die Admin-Login-Anfrage."""

    username: str
    password: str


class Token(BaseModel):
    """Schema für das Access Token."""

    access_token: str
    token_type: str  # Üblicherweise "bearer"


class AnswerDetail(BaseModel):
    """Detail einer einzelnen Antwort für die Admin-Ansicht."""

    survey_element_id: int
    element_type: str
    response_value: Optional[Any] = None
    llm_chat_history: Optional[List[ChatMessage]] = None
    question_text: Optional[str] = None
    question_type: Optional[str] = None
    task_identifier: Optional[str] = None
    references_element_id: Optional[int] = None
    randomization_group: Optional[str] = None

    # Tracking-Felder pro Antwort
    paste_count: Optional[int] = None
    focus_lost_count: Optional[int] = None

    # Für Export: DB ID und Erstellungsdatum der Antwort
    id: int
    created_at: datetime
    displayed_page: Optional[int] = None
    displayed_ordering: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class ParticipantResultDetail(BaseModel):
    """Details eines Teilnehmers und seiner Antworten."""

    participant_id: int
    prolific_pid: Optional[str] = None
    study_id: Optional[str] = None
    session_id: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    consent_given: bool
    completed: bool
    responses: List[AnswerDetail] = []

    page_durations_log: Optional[Dict[str, int]] = None

    model_config = ConfigDict(from_attributes=True)


class SurveyResultsAdminResponse(BaseModel):
    """Gesamte Ergebnisübersicht für eine Umfrage für den Admin."""

    survey_id: int
    title: str
    total_participants: int
    participants: List[ParticipantResultDetail] = []

    model_config = ConfigDict(from_attributes=True)


# Für flachen Export - repräsentieren direkt die DB-Tabellen
class SurveyElementExport(SurveyElementBase):
    id: int
    survey_id: int
    model_config = ConfigDict(from_attributes=True)


class ResponseExport(BaseModel):
    id: int
    participant_id: int
    survey_element_id: int
    response_value: Optional[Any] = None
    created_at: datetime
    llm_chat_history: Optional[List[ChatMessage]] = None
    paste_count: Optional[int] = None
    focus_lost_count: Optional[int] = None
    displayed_page: Optional[int] = None
    displayed_ordering: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class SurveyParticipantExport(BaseModel):
    id: int
    survey_id: int
    prolific_pid: Optional[str] = None
    study_id: Optional[str] = None
    session_id: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    consent_given: bool
    completed: bool
    page_durations_log: Optional[Dict[str, int]] = None
    model_config = ConfigDict(from_attributes=True)


class SurveyExport(SurveyBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Schema für den flachen Gesamtexport
class AllDataFlatExport(BaseModel):
    surveys: List[SurveyExport]
    survey_elements: List[SurveyElementExport]
    survey_participants: List[SurveyParticipantExport]
    responses: List[ResponseExport]


# Schema für den verschachtelten Gesamtexport
# Schema, das SurveyResponse und ParticipantResultDetail kombiniert
class SurveyFullNestedExport(
    SurveyResponse
):  # Erbt von SurveyResponse (hat Titel, Elemente  etc.)
    participants_results: List[
        ParticipantResultDetail
    ] = []  # Füge Teilnehmerergebnisse hinzu
    model_config = ConfigDict(from_attributes=True)


class AllDataNestedExport(BaseModel):
    surveys: List[SurveyFullNestedExport]
