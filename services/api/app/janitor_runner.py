# services/api/app/janitor_runner.py

import os
import time
import logging

from sqlalchemy.orm import Session as OrmSession

from .db import SessionLocal
from .janitor import run_retention_cleanup

LOG = logging.getLogger("skinguide.janitor")

def main():
    sleep_seconds = int(os.getenv("JANITOR_SLEEP_SECONDS", "21600"))  # 6 hours
    while True:
        try:
            db: OrmSession = SessionLocal()
            try:
                res = run_retention_cleanup(db)
                LOG.info(f"cleanup_ok {res}")
            finally:
                db.close()
        except Exception as e:
            LOG.exception(f"cleanup_failed: {e}")

        time.sleep(sleep_seconds)

if __name__ == "__main__":
    main()
