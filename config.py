from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MTJL Technology — Site institucional"
    app_env: str = "development"  # set APP_ENV=production no servidor
    database_url: str = "sqlite:////private/tmp/mtjl_website.db"
    resend_api_key: str = ""
    asaas_api_key: str = ""
    asaas_webhook_token: str = ""
    pilotqa_jwt_private_key: str = ""
    booking_internal_url: str = "http://127.0.0.1:8000"
    booking_master_api_key: str = "change-me-in-production"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
