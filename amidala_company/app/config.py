from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    app_name: str = "Amidala"
    base_url: str = "http://127.0.0.1:8000"
    admin_password: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = ""
    smtp_to: str = ""
    stripe_secret_key: str = ""
    stripe_success_url: str = ""
    stripe_cancel_url: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
