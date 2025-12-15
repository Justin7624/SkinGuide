# services/api/app/config.py

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    ML_URL: str

    STORE_IMAGES_DEFAULT: bool = False
    STORE_IMAGES_ENABLED: bool = False
    DONATION_STORAGE_ENABLED: bool = False

    STORAGE_BACKEND: str = "local"  # "local" or "s3"
    S3_BUCKET: str | None = None
    S3_PREFIX: str = "skinguide"
    AWS_REGION: str | None = None
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None

    IMAGE_STORE_DIR: str = "/data/images"
    DONATION_STORE_DIR: str = "/data/donations"

    # Legacy admin key (disable by leaving unset)
    ADMIN_API_KEY: str | None = None

    # RBAC bootstrap: allow creating the FIRST admin user if none exists.
    # Send as header: X-Bootstrap-Token
    ADMIN_BOOTSTRAP_TOKEN: str | None = None

    # Admin web sessions (server-side)
    ADMIN_SESSION_TTL_MIN: int = 60 * 12  # 12 hours
    ADMIN_COOKIE_NAME: str = "admin_session"
    ADMIN_COOKIE_SECURE: bool = False     # set True behind HTTPS in production
    ADMIN_COOKIE_SAMESITE: str = "lax"    # "lax" recommended
    ADMIN_COOKIE_DOMAIN: str | None = None

    # Password reset (email sending is out of scope; we scaffold token issuance)
    PASSWORD_RESET_TTL_MIN: int = 30
    PASSWORD_RESET_DEBUG_RETURN_TOKEN: bool = True  # set False in production

    MODEL_SHARED_DIR: str = "/models"
    MODEL_CURRENT_MANIFEST_PATH: str = "/models/current/manifest.json"
    MODEL_CURRENT_PT_PATH: str = "/models/current/model.pt"

    SESSION_SECRET: str
    REQUIRE_AUTH: bool = False
    ACCESS_TOKEN_TTL_MIN: int = 60 * 24 * 30  # 30 days

    RATE_LIMIT_PER_MIN: int = 20
    RATE_LIMIT_FAIL_OPEN: bool = True

    MAX_IMAGE_MB: int = 6
    MAX_IMAGE_PIXELS: int = 12_000_000
    MIN_IMAGE_DIM: int = 320
    MAX_IMAGE_DIM: int = 4096

    PROGRESS_RETENTION_DAYS: int = 180
    WITHDRAWN_DONATION_RETENTION_DAYS: int | None = None

    # -------------------------
    # Labeling consensus tuning
    # -------------------------
    LABEL_CONSENSUS_N: int = 2  # set to 3 for 3-labeler consensus
    LABEL_MEAN_ABS_DIFF_MAX: float = 0.35
    LABEL_MAX_ABS_DIFF_MAX: float = 0.60

    # IRR stats compute cap
    IRR_MAX_SAMPLES: int = 5000

settings = Settings()
