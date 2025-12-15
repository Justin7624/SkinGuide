# services/api/app/config.py

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    ML_URL: str

    STORE_IMAGES_DEFAULT: bool = False
    STORE_IMAGES_ENABLED: bool = False

    DONATION_STORAGE_ENABLED: bool = False

    # Storage
    STORAGE_BACKEND: str = "local"  # "local" or "s3"
    S3_BUCKET: str | None = None
    S3_PREFIX: str = "skinguide"
    AWS_REGION: str | None = None
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None

    # Local roots (used by local backend only)
    IMAGE_STORE_DIR: str = "/data/images"
    DONATION_STORE_DIR: str = "/data/donations"

    # Admin / rollout
    ADMIN_API_KEY: str | None = None
    MODEL_SHARED_DIR: str = "/models"
    MODEL_CURRENT_MANIFEST_PATH: str = "/models/current/manifest.json"
    MODEL_CURRENT_PT_PATH: str = "/models/current/model.pt"

    # Auth
    SESSION_SECRET: str
    REQUIRE_AUTH: bool = False  # set true in production
    ACCESS_TOKEN_TTL_MIN: int = 60 * 24 * 30  # 30 days

    RATE_LIMIT_PER_MIN: int = 20
    MAX_IMAGE_MB: int = 6

settings = Settings()
