# services/api/app/schemas_me.py

from pydantic import BaseModel

class DeleteMeResponse(BaseModel):
    ok: bool
    deleted_progress_entries: int = 0
    withdrawn_donations: int = 0
    deleted_consent: bool = False
    deleted_session: bool = False
