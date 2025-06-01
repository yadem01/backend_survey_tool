from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    JSON,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func  # Für Default-Zeitstempel
from .database import Base  # Importiere die Base aus database.py


# Beispiel: Survey Tabelle (vereinfacht)
class Survey(Base):
    __tablename__ = "surveys"  # Name der Tabelle in der DB

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String, index=True)
    description = Column(Text, nullable=True)
    config = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), onupdate=func.now(), server_default=func.now()
    )

    prolific_enabled = Column(Boolean, default=False)
    prolific_completion_url = Column(String, nullable=True)

    # FELDER für erweitertes Tracking & Zeitmanagement Konfiguration
    enable_advanced_tracking = Column(Boolean, default=False)  # Globaler Schalter
    track_copy_paste = Column(Boolean, default=False)  # Copy-Paste Tracking aktivieren?
    track_tab_focus = Column(Boolean, default=False)  # Tab-Fokus Tracking aktivieren?
    track_page_duration = Column(Boolean, default=False)  # Zeit pro Seite messen?
    display_time_spent = Column(Boolean, default=False)  # Verstrichene Zeit anzeigen?
    enable_max_duration = Column(Boolean, default=False)  # Max. Dauer aktivieren?
    max_duration_minutes = Column(Integer, nullable=True)  # Max. Dauer in Minuten
    max_duration_warning_minutes = Column(
        Integer, nullable=True
    )  # Vorwarnzeit in Minuten

    # Beziehung zu SurveyElement (eine Umfrage hat viele Elemente)
    elements = relationship(
        "SurveyElement", back_populates="survey", cascade="all, delete-orphan"
    )
    # Beziehung zu Participants (eine Umfrage hat viele Teilnehmer)
    participants = relationship("SurveyParticipant", back_populates="survey")


# Beispiel: SurveyElement Tabelle (vereinfacht)
class SurveyElement(Base):
    __tablename__ = "survey_elements"

    id = Column(Integer, primary_key=True, index=True)
    survey_id = Column(Integer, ForeignKey("surveys.id"))  # Fremdschlüssel zu Survey
    element_type = Column(String)  # 'info', 'consent', 'question' etc.
    question_type = Column(
        String, nullable=True
    )  # 'shorttext', 'likert' etc. (nur für type='question')
    question_text = Column(Text, nullable=True)
    options = Column(JSON, nullable=True)  # Antwortoptionen als JSON
    ordering = Column(Integer, default=0)
    page = Column(Integer, default=1)
    image_url = Column(String, nullable=True)
    required = Column(Boolean, default=False)
    paste_disabled = Column(Boolean, default=False)
    randomization_group = Column(String, nullable=True)
    allow_back_navigation = Column(Boolean, default=True)
    llm_assistance_enabled = Column(Boolean, default=False)
    maxlength = Column(Integer, nullable=True)
    task_identifier = Column(
        String, nullable=True, index=True
    )  # Zur Gruppierung von Elementen zu einem Task
    references_element_id = Column(
        Integer, ForeignKey("survey_elements.id"), nullable=True
    )  # Verweis auf ein anderes Element

    # Beziehung zurück zu Survey
    survey = relationship("Survey", back_populates="elements")

    # Optionale Beziehung für den self-referential ForeignKey (um z.B. das referenzierte Element leicht zu laden)
    # referenced_element = relationship("SurveyElement", remote_side=[id], foreign_keys=[references_element_id], uselist=False)
    # responses_to_reference = relationship("SurveyElement", back_populates="referenced_element", foreign_keys=[references_element_id], remote_side=[id])


class SurveyParticipant(Base):
    __tablename__ = "survey_participants"
    id = Column(Integer, primary_key=True, index=True)
    survey_id = Column(Integer, ForeignKey("surveys.id"))

    # Felder für Prolific Integration
    prolific_pid = Column(String, unique=True, index=True, nullable=True)
    study_id = Column(String, index=True, nullable=True)  # Prolific Study ID
    session_id = Column(String, index=True, nullable=True)  # Prolific Session ID

    start_time = Column(DateTime(timezone=True), server_default=func.now())
    end_time = Column(DateTime(timezone=True), nullable=True)
    consent_given = Column(Boolean, default=False)
    completed = Column(Boolean, default=False)

    page_durations_log = Column(
        JSON, nullable=True
    )  # z.B. {"1": 30500, "2": 45200} (Seite: ms)

    survey = relationship("Survey", back_populates="participants")
    responses = relationship(
        "Response", back_populates="participant", cascade="all, delete-orphan"
    )


class Response(Base):
    __tablename__ = "responses"
    id = Column(Integer, primary_key=True, index=True)
    participant_id = Column(Integer, ForeignKey("survey_participants.id"))
    survey_element_id = Column(
        Integer, ForeignKey("survey_elements.id")
    )  # ID der Frage/Elements
    response_value = Column(
        JSON
    )  # Antwort als JSON speichern (flexibel für Text, Array etc.)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    llm_chat_history = Column(JSON, nullable=True)

    paste_count = Column(
        Integer, nullable=True, default=0
    )  # Anzahl Copy-Paste-Versuche
    focus_lost_count = Column(
        Integer, nullable=True, default=0
    )  # Anzahl Tab/Fokus-Verluste

    displayed_page = Column(Integer, nullable=True)
    displayed_ordering = Column(Integer, nullable=True)

    participant = relationship("SurveyParticipant", back_populates="responses")
