from sqlalchemy.orm import Session
from app.models.survey import Survey
from app.schemas.survey import SurveyCreate, SurveyUpdate


def create_survey(db: Session, survey_in: SurveyCreate) -> Survey:
    db_survey = Survey(
        question_text=survey_in.question_text,
        question_type=survey_in.question_type,
        options=survey_in.options,
        tracking_flags=survey_in.tracking_flags,
        ordering=survey_in.ordering,
    )
    db.add(db_survey)
    db.commit()
    db.refresh(db_survey)
    return db_survey


def get_survey(db: Session, survey_id: int) -> Survey:
    return db.query(Survey).filter(Survey.id == survey_id).first()


def get_all_surveys(db: Session):
    return db.query(Survey).order_by(Survey.ordering).all()


def update_survey(db: Session, db_survey: Survey, survey_in: SurveyUpdate) -> Survey:
    db_survey.question_text = survey_in.question_text
    db_survey.question_type = survey_in.question_type
    db_survey.options = survey_in.options
    db_survey.tracking_flags = survey_in.tracking_flags
    db_survey.ordering = survey_in.ordering
    db.commit()
    db.refresh(db_survey)
    return db_survey


def delete_survey(db: Session, survey_id: int):
    db_survey = get_survey(db, survey_id)
    if db_survey:
        db.delete(db_survey)
        db.commit()
    return db_survey
