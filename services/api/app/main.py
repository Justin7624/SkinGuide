# services/api/app/main.py

from fastapi import FastAPI
from .routes_session import router as session_router
from .routes_consent import router as consent_router
from .routes_analyze import router as analyze_router
from .routes_progress import router as progress_router
from .routes_donate import router as donate_router
from .routes_label import router as label_router
from .routes_model import router as model_router

app = FastAPI(title="SkinGuide API", version="0.5.0")

app.include_router(session_router)
app.include_router(consent_router)
app.include_router(analyze_router)
app.include_router(progress_router)
app.include_router(donate_router)
app.include_router(label_router)
app.include_router(model_router)

@app.get("/health")
def health():
    return {"ok": True}
