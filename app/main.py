from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.resources import router as resource_router
from app.database.database import Base, engine
from app.models.resource import Resource
from app.models.state_history import StateHistory
from app.models.idempotency_record import IdempotencyRecord



@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Distributed Infrastructure Control Plane",
    description=(
        "A distributed control plane with eventual consistency "
        "and state reconciliation."
    ),
    version="0.1.0",
)

app.include_router(resource_router)


@app.get("/")
async def root():
    return {
        "service": "Distributed Infrastructure Control Plane",
        "status": "running",
        "version": "0.1.0",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
    }
