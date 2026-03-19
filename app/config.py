import os


class Settings:
    def __init__(self) -> None:
        self.database_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://ofisarama:ofisarama@localhost:5432/ofisarama_v2",
        )


settings = Settings()
