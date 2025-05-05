from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime

# Basismodell für eine Antwort (wie sie vom Frontend kommen könnte)
class AnswerBase(BaseModel):
    question_id: int = Field(..., description="ID des SurveyElement (Frage)")
    value: Union[str, List[str], int, float, bool, None] = Field(..., description="Gegebene Antwort")

# Modell für die gesamten Ergebnisse, die vom Frontend gesendet werden
class SurveyResultCreate(BaseModel):
    prolific_pid: Optional[str] = Field(None, description="Prolific Participant ID")
    study_id: Optional[str] = Field(None, description="Prolific Study ID")
    session_id: Optional[str] = Field(None, description="Prolific Session ID")
    consent_given: bool = Field(..., description="Hat der Nutzer zugestimmt?")
    answers: Dict[str, Union[str, List[str], int, float, bool, None]] = Field(..., description="Dictionary der Antworten {question_id: value}")
    # TODO: Hier könnten noch Tracking-Daten (Zeiten, Tab-Wechsel etc.) hinzukommen

# Modell für die Antwort nach erfolgreichem Speichern (Beispiel)
class SurveyResultResponse(BaseModel):
    participant_id: int
    message: str = "Ergebnisse erfolgreich gespeichert."

# Pydantic Modelle für Survey und SurveyElement (optional, nützlich für API-Antworten)
class SurveyElementSchema(BaseModel):
    id: int
    element_type: str
    question_type: Optional[str] = None
    question_text: Optional[str] = None
    options: Optional[Any] = None # Any für Flexibilität bei JSON
    ordering: int
    page: int
    # ... weitere Felder nach Bedarf ...

    class Config:
        from_attributes = True # Erlaubt das Erstellen aus SQLAlchemy-Objekten

class SurveySchema(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    # elements: List[SurveyElementSchema] = [] # Optional: Elemente direkt mitsenden

    class Config:
        from_attributes = True # Erlaubt das Erstellen aus SQLAlchemy-Objekten