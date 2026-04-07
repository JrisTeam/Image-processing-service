from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "sqlite+aiosqlite:///./dev.db"
    JWT_SECRET: str = "changeme"

    # S3-compatible storage (works with floci, Cloudflare R2, MinIO, etc.)
    S3_ENDPOINT_URL: str = "http://floci:4566"
    S3_ACCESS_KEY_ID: str = "test"
    S3_SECRET_ACCESS_KEY: str = "test"
    S3_BUCKET_NAME: str = "images"
    S3_PUBLIC_URL: str = "http://localhost:4566/images"
    S3_REGION: str = "us-east-1"

    REDIS_URL: str = "redis://localhost:6379"


settings = Settings()
