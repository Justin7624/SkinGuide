# services/api/app/main.py

from fastapi import FastAPI
from .logging_mw import RequestLoggingMiddleware, configure_logging

from .routes_session import router as session_router
from .routes_consent import router as consent_router
from .routes_legal import router as legal_router

from .routes_admin import router as admin_router
from .routes_admin_web import router as admin_web_router
from .routes_admin_auth import router as admin_auth_router
from .routes_admin_users import router as admin_users_router
from .routes_admin_labelqueue import router as admin_labelqueue_router

from .routes_analyze import router as analyze_router
from .routes_progress import router as progress_router
from .routes_donate import router as donate_router
from .routes_label import router as label_router
from .routes_model import router as model_router
from .routes_me import router as me_router

app = FastAPI(title="SkinGuide API", version="0.9.0")

configure_logging()
app.add_middleware(RequestLoggingMiddleware)

app.include_router(session_router)
app.include_router(consent_router)
app.include_router(legal_router)

app.include_router(admin_router)
app.include_router(admin_auth_router)
app.include_router(admin_users_router)
app.include_router(admin_labelqueue_router)
app.include_router(admin_web_router)  # GET /admin

app.include_router(analyze_router)
app.include_router(progress_router)
app.include_router(donate_router)
app.include_router(label_router)
app.include_router(model_router)
app.include_router(me_router)

@app.get("/health")
def health():
    return {"ok": True}
