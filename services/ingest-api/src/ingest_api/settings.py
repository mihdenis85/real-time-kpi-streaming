from functools import lru_cache
from pathlib import Path

from dynaconf import Dynaconf
from pydantic import BaseModel, ConfigDict, Field

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseModel):
    model_config = ConfigDict(extra="allow")

    SERVICE_NAME: str = Field(..., description="Name of the service")
    VERSION: str = Field(..., description="Service version")
    ROOT_PATH: str = Field("", description="API root path")

    HOST: str = Field("0.0.0.0", description="Bind host")
    PORT: int = Field(8000, description="Bind port")
    LOG_LEVEL: str = Field("INFO", description="Logging level")
    LOG_EVERY_N: int = Field(100, description="Log every N events")
    ALLOWED_ORIGINS: list[str] = Field(default_factory=lambda: ["*"])

    KAFKA_BOOTSTRAP_SERVERS: str = Field(..., description="Kafka bootstrap servers")
    KAFKA_ORDERS_TOPIC: str = Field("orders", description="Orders topic")
    KAFKA_SESSIONS_TOPIC: str = Field("sessions", description="Sessions topic")
    KAFKA_CLIENT_ID: str = Field("ingest-api", description="Kafka client id")

    DB_DSN: str = Field(..., description="PostgreSQL DSN")


dynaconf_settings = Dynaconf(
    envvar_prefix="INGEST_API",
    environments=True,
    settings_files=[BASE_DIR / "settings.toml", BASE_DIR / ".secrets.toml"],
    root_path=BASE_DIR,
    load_dotenv=False,
)


@lru_cache
def get_settings() -> Settings:
    return Settings(**dynaconf_settings)  # type: ignore[arg-type]
