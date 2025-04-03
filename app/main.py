from fastapi import FastAPI
from app.api.endpoints import survey, response
from app.core.database import Base, engine

# Create the DB tables if they don't exist
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Survey Tool",
    version="1.0.0",
)

# Include routers for Survey & Response
app.include_router(survey.router, prefix="/survey", tags=["survey"])
app.include_router(response.router, prefix="/responses", tags=["response"])
