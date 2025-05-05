from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, ForeignKey, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func # Für Default-Zeitstempel
from database import Base # Importiere die Base aus database.py

# Beispiel: Survey Tabelle (vereinfacht)
class Survey(Base):
    __tablename__ = "surveys" # Name der Tabelle in der DB

    id = Column(Integer, primary_key=True, index=True) # Automatisch hochzählend
    title = Column(String, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    # config = Column(JSON) # Speichert config als JSON

    # Beziehung zu SurveyElement (eine Umfrage hat viele Elemente)
    elements = relationship("SurveyElement", back_populates="survey")
    # Beziehung zu Participants (eine Umfrage hat viele Teilnehmer)
    participants = relationship("SurveyParticipant", back_populates="survey")

# Beispiel: SurveyElement Tabelle (vereinfacht)
class SurveyElement(Base):
    __tablename__ = "survey_elements"

    id = Column(Integer, primary_key=True, index=True)
    survey_id = Column(Integer, ForeignKey("surveys.id")) # Fremdschlüssel zu Survey
    element_type = Column(String) # 'info', 'consent', 'question' etc.
    question_type = Column(String, nullable=True) # 'shorttext', 'likert' etc. (nur für type='question')
    question_text = Column(Text, nullable=True)
    options = Column(JSON, nullable=True) # Antwortoptionen als JSON
    ordering = Column(Integer, default=0)
    page = Column(Integer, default=1)
    image_url = Column(String, nullable=True)
    required = Column(Boolean, default=False)
    paste_disabled = Column(Boolean, default=False)
    randomization_group = Column(String, nullable=True)
    allow_back_navigation = Column(Boolean, default=True)

    # Beziehung zurück zu Survey
    survey = relationship("Survey", back_populates="elements")

# TODO: Weitere Modelle hinzufügen (SurveyParticipant, Response, UserTracking)
# basierend auf deinem Datenbankentwurf.

# Beispiel: SurveyParticipant
class SurveyParticipant(Base):
    __tablename__ = "survey_participants"
    id = Column(Integer, primary_key=True, index=True)
    survey_id = Column(Integer, ForeignKey("surveys.id"))
    prolific_pid = Column(String, unique=True, index=True, nullable=True) # Eindeutig pro Studie?
    # ... andere Felder wie consent_given, completed, start_time, end_time ...
    start_time = Column(DateTime(timezone=True), server_default=func.now())
    end_time = Column(DateTime(timezone=True), nullable=True)
    consent_given = Column(Boolean, default=False)
    completed = Column(Boolean, default=False)

    survey = relationship("Survey", back_populates="participants")
    responses = relationship("Response", back_populates="participant")

# Beispiel: Response
class Response(Base):
    __tablename__ = "responses"
    id = Column(Integer, primary_key=True, index=True)
    participant_id = Column(Integer, ForeignKey("survey_participants.id"))
    survey_element_id = Column(Integer, ForeignKey("survey_elements.id")) # ID der Frage/Elements
    response_value = Column(JSON) # Antwort als JSON speichern (flexibel für Text, Array etc.)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    participant = relationship("SurveyParticipant", back_populates="responses")
    # Optional: Beziehung zu SurveyElement, falls benötigt