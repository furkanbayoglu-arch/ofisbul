import os


class Settings:
    def __init__(self) -> None:
        self.database_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://ofisarama:ofisarama@localhost:5432/ofisarama_v2",
        )
        self.session_secret = os.environ.get(
            "SESSION_SECRET",
            "ofisarama-v2-dev-session-secret-change-me",
        )
        self.bootstrap_admin_email = os.environ.get(
            "BOOTSTRAP_ADMIN_EMAIL",
            "admin@ofisarama.local",
        )
        self.bootstrap_admin_password = os.environ.get(
            "BOOTSTRAP_ADMIN_PASSWORD",
            "change-this-password",
        )
        self.bootstrap_admin_name = os.environ.get(
            "BOOTSTRAP_ADMIN_NAME",
            "OfisArama Admin",
        )


settings = Settings()
