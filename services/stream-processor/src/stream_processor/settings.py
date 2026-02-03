from functools import lru_cache
from pathlib import Path

from dynaconf import Dynaconf
from pydantic import BaseModel, ConfigDict, Field

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseModel):
    model_config = ConfigDict(extra="allow")

    SERVICE_NAME: str = Field(..., description="Name of the service")
    VERSION: str = Field(..., description="Service version")

    LOG_LEVEL: str = Field("INFO", description="Logging level")
    FLUSH_INTERVAL_SECONDS: int = Field(10, description="Flush interval in seconds")
    DEDUPE_TTL_SECONDS: int = Field(300, description="Deduplication TTL in seconds")
    LOG_EVERY_N: int = Field(200, description="Log every N events")

    KAFKA_BOOTSTRAP_SERVERS: str = Field(..., description="Kafka bootstrap servers")
    KAFKA_ORDERS_TOPIC: str = Field("orders", description="Orders topic")
    KAFKA_SESSIONS_TOPIC: str = Field("sessions", description="Sessions topic")
    KAFKA_GROUP_ID: str = Field("stream-processor", description="Kafka group id")
    KAFKA_AUTO_OFFSET_RESET: str = Field("earliest", description="Offset reset policy")

    DB_DSN: str = Field(..., description="PostgreSQL DSN")


dynaconf_settings = Dynaconf(
    envvar_prefix="STREAM_PROCESSOR",
    environments=True,
    settings_files=[BASE_DIR / "settings.toml", BASE_DIR / ".secrets.toml"],
    root_path=BASE_DIR,
    load_dotenv=False,
)


@lru_cache
def get_settings() -> Settings:
    return Settings(**dynaconf_settings)  # type: ignore[arg-type]
