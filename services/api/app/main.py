# services/api/app/main.py

from fastapi import FastAPI
from .db import Base, engine
from .routes_consent import router as consent_router
from .routes_analyze import router as analyze_router
from .routes_progress import router as progress_router
from .routes_donate import router as donate_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="SkinGuide API", version="0.2.0")

app.include_router(consent_router)
app.include_router(analyze_router)
app.include_router(progress_router)
app.include_router(donate_router)

@app.get("/health")
def health():
    return {"ok": True}
