from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app import crud
from app.schemas.response import Response, ResponseCreate, ResponseUpdate

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=Response)
def create_response_item(resp_in: ResponseCreate, db: Session = Depends(get_db)):
    return crud.crud_response.create_response(db, resp_in)


@router.get("/{r_id}", response_model=Response)
def read_response_item(r_id: int, db: Session = Depends(get_db)):
    db_resp = crud.crud_response.get_response(db, r_id)
    if not db_resp:
        raise HTTPException(status_code=404, detail="Response not found")
    return db_resp


@router.put("/{r_id}", response_model=Response)
def update_response_item(
    r_id: int, resp_in: ResponseUpdate, db: Session = Depends(get_db)
):
    db_resp = crud.crud_response.get_response(db, r_id)
    if not db_resp:
        raise HTTPException(status_code=404, detail="Response not found")
    return crud.crud_response.update_response(db, db_resp, resp_in)


@router.delete("/{r_id}", response_model=Response)
def delete_response_item(r_id: int, db: Session = Depends(get_db)):
    db_resp = crud.crud_response.get_response(db, r_id)
    if not db_resp:
        raise HTTPException(status_code=404, detail="Response not found")
    return crud.crud_response.delete_response(db, r_id)
