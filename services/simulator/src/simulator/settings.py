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
    ENABLED: bool = Field(True, description="Enable simulator loop")

    API_BASE_URL: str = Field(..., description="Ingest API base URL")
    API_KEY: str = Field(..., description="API key header")
    SEND_INTERVAL_SECONDS: int = Field(5, description="Send interval in seconds")

    BASE_ORDERS_PER_TICK: int = Field(3, description="Base orders per tick")
    ORDER_COUNT_JITTER: float = Field(1.0, description="Orders jitter")
    BASE_SESSIONS_PER_TICK: int = Field(6, description="Base sessions per tick")
    SESSION_COUNT_JITTER: float = Field(2.0, description="Sessions jitter")

    ORDER_BASE_AMOUNT_RUB: float = Field(1200.0, description="Base order amount")
    ORDER_AMOUNT_STDDEV: float = Field(150.0, description="Amount stddev")

    CHANNELS: list[str] = Field(default_factory=lambda: ["web", "ads", "marketplace"])
    CAMPAIGNS: list[str] = Field(default_factory=lambda: ["spring", "promo", "brand"])

    CHECKOUT_RATE: float = Field(0.35, description="Checkout probability")
    PURCHASE_RATE: float = Field(0.12, description="Purchase probability")

    ANOMALY_PROB: float = Field(0.03, description="Anomaly probability per tick")
    ANOMALY_LOW_MULTIPLIER: float = Field(0.4, description="Low anomaly factor")
    ANOMALY_HIGH_MULTIPLIER: float = Field(2.0, description="High anomaly factor")

    SEED: int | None = Field(None, description="Random seed")


dynaconf_settings = Dynaconf(
    envvar_prefix="SIMULATOR",
    environments=True,
    settings_files=[BASE_DIR / "settings.toml", BASE_DIR / ".secrets.toml"],
    root_path=BASE_DIR,
    load_dotenv=False,
)


@lru_cache
def get_settings() -> Settings:
    return Settings(**dynaconf_settings)  # type: ignore[arg-type]
