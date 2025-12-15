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

    ADMIN_API_KEY: str | None = None
    MODEL_SHARED_DIR: str = "/models"
    MODEL_CURRENT_MANIFEST_PATH: str = "/models/current/manifest.json"
    MODEL_CURRENT_PT_PATH: str = "/models/current/model.pt"

    SESSION_SECRET: str
    REQUIRE_AUTH: bool = False
    ACCESS_TOKEN_TTL_MIN: int = 60 * 24 * 30

    RATE_LIMIT_PER_MIN: int = 20
    RATE_LIMIT_FAIL_OPEN: bool = True

    MAX_IMAGE_MB: int = 6
    MAX_IMAGE_PIXELS: int = 12_000_000
    MIN_IMAGE_DIM: int = 320
    MAX_IMAGE_DIM: int = 4096

    # Retention
    PROGRESS_RETENTION_DAYS: int = 180
    # Donations are for model improvement; default is KEEP.
    # If you want hard deletion of WITHDRAWN donations after some time, set this (e.g. 30).
    WITHDRAWN_DONATION_RETENTION_DAYS: int | None = None

settings = Settings()
