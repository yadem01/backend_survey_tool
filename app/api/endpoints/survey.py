from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app import crud
from app.schemas.survey import Survey, SurveyCreate, SurveyUpdate

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=Survey)
def create_survey_item(survey_in: SurveyCreate, db: Session = Depends(get_db)):
    return crud.crud_survey.create_survey(db, survey_in)


@router.get("/{survey_id}", response_model=Survey)
def read_survey_item(survey_id: int, db: Session = Depends(get_db)):
    db_survey = crud.crud_survey.get_survey(db, survey_id)
    if not db_survey:
        raise HTTPException(status_code=404, detail="Survey not found")
    return db_survey


@router.get("/", response_model=list[Survey])
def read_all_surveys(db: Session = Depends(get_db)):
    return crud.crud_survey.get_all_surveys(db)


@router.put("/{survey_id}", response_model=Survey)
def update_survey_item(
    survey_id: int, survey_in: SurveyUpdate, db: Session = Depends(get_db)
):
    db_survey = crud.crud_survey.get_survey(db, survey_id)
    if not db_survey:
        raise HTTPException(status_code=404, detail="Survey not found")
    return crud.crud_survey.update_survey(db, db_survey, survey_in)


@router.delete("/{survey_id}", response_model=Survey)
def delete_survey_item(survey_id: int, db: Session = Depends(get_db)):
    db_survey = crud.crud_survey.get_survey(db, survey_id)
    if not db_survey:
        raise HTTPException(status_code=404, detail="Survey not found")
    return crud.crud_survey.delete_survey(db, survey_id)
