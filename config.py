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
    # Token da propriedade www.larclinicahealth.com no Google Search Console. Vazio
    # é o normal depois que a propriedade já está verificada: a meta tag só precisa
    # existir no momento da verificação, mas o Google pede que ela continue no ar.
    larclinica_google_site_verification: str = ""
    # reCAPTCHA v3 nos formulários de contato. A chave secreta é a do mesmo
    # par cuja site key já está nas páginas (Google Cloud → reCAPTCHA
    # Enterprise/v3). Vazia desliga a verificação: o formulário continua
    # protegido por honeypot, blocklist e filtro de assinatura de bot, mas o
    # score do Google deixa de ser consultado.
    recaptcha_secret_key: str = ""
    # Score mínimo do v3 para aceitar a submissão. 0.0 = certamente bot,
    # 1.0 = certamente humano. 0.5 é o corte sugerido pelo Google; abaixar
    # se lead legítimo estiver sendo descartado.
    recaptcha_min_score: float = 0.5

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
