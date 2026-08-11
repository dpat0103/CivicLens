from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine
from .routers import locations, compare

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="CivicLens API",
    description="Location intelligence built from normalized public datasets: "
                 "housing, employment, safety, transportation, and population.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(locations.router)
app.include_router(compare.router)


@app.get("/", tags=["health"])
def health():
    return {"status": "ok", "service": "civiclens-api"}
