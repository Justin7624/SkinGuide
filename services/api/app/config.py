from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    ML_URL: str

    STORE_IMAGES_DEFAULT: bool = False
    STORE_IMAGES_ENABLED: bool = False
    IMAGE_STORE_DIR: str = "/data/images"

    SESSION_SECRET: str
    RATE_LIMIT_PER_MIN: int = 20
    MAX_IMAGE_MB: int = 6

settings = Settings()
