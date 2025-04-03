from sqlalchemy.orm import Session
from app.models.response import Response
from app.schemas.response import ResponseCreate, ResponseUpdate
from datetime import datetime


def create_response(db: Session, response_in: ResponseCreate) -> Response:
    db_response = Response(
        q_id=response_in.q_id,
        p_id=response_in.p_id,
        answer_txt=response_in.answer_txt,
        # TO DO: needs to calculate time_spent on the server side
        time_spent=response_in.time_spent,
        meta=response_in.meta,
    )
    db.add(db_response)
    db.commit()
    db.refresh(db_response)
    return db_response


def get_response(db: Session, r_id: int) -> Response:
    return db.query(Response).filter(Response.r_id == r_id).first()


def get_responses_for_question(db: Session, q_id: int):
    return db.query(Response).filter(Response.q_id == q_id).all()


def update_response(
    db: Session, db_response: Response, resp_in: ResponseUpdate
) -> Response:
    db_response.q_id = resp_in.q_id
    db_response.p_id = resp_in.p_id
    db_response.answer_txt = resp_in.answer_txt
    db_response.time_spent = resp_in.time_spent
    db_response.meta = resp_in.meta
    db.commit()
    db.refresh(db_response)
    return db_response


def delete_response(db: Session, r_id: int):
    db_response = get_response(db, r_id)
    if db_response:
        db.delete(db_response)
        db.commit()
    return db_response
