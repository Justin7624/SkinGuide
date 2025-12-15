# services/api/app/janitor.py

from datetime import datetime, timedelta
from sqlalchemy.orm import Session as OrmSession

from .config import settings
from .storage import get_storage
from . import models

def run_retention_cleanup(db: OrmSession) -> dict:
    """
    - Deletes progress entries older than PROGRESS_RETENTION_DAYS (and their stored ROI images).
    - Optionally hard-deletes WITHDRAWN donated samples older than WITHDRAWN_DONATION_RETENTION_DAYS.
      (Non-withdrawn donations are never auto-deleted here.)
    """
    storage = get_storage()
    now = datetime.utcnow()

    progress_cutoff = now - timedelta(days=int(settings.PROGRESS_RETENTION_DAYS))
    old_progress = db.query(models.ProgressEntry).filter(models.ProgressEntry.created_at < progress_cutoff).all()

    deleted_progress = 0
    for p in old_progress:
        if p.roi_image_path:
            storage.delete_uri(p.roi_image_path)
        db.delete(p)
        deleted_progress += 1

    deleted_withdrawn = 0
    if settings.WITHDRAWN_DONATION_RETENTION_DAYS is not None:
        wd_cutoff = now - timedelta(days=int(settings.WITHDRAWN_DONATION_RETENTION_DAYS))
        old_withdrawn = (
            db.query(models.DonatedSample)
            .filter(models.DonatedSample.is_withdrawn == True)   # noqa: E712
            .filter(models.DonatedSample.withdrawn_at != None)   # noqa: E711
            .filter(models.DonatedSample.withdrawn_at < wd_cutoff)
            .all()
        )
        for d in old_withdrawn:
            # image likely already deleted during withdrawal, but try again
            if d.roi_image_path:
                storage.delete_uri(d.roi_image_path)
            db.delete(d)
            deleted_withdrawn += 1

    db.commit()

    return {
        "deleted_progress_entries": deleted_progress,
        "deleted_withdrawn_donations": deleted_withdrawn,
        "progress_cutoff": progress_cutoff.isoformat(),
    }
