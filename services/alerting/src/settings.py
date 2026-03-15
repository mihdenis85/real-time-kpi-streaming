from functools import lru_cache
from pathlib import Path

from dynaconf import Dynaconf
from pydantic import BaseModel, ConfigDict, Field

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseModel):
    model_config = ConfigDict(extra="allow")

    SERVICE_NAME: str = Field(..., description="Name of the service")
    VERSION: str = Field(..., description="Service version")

    LOG_LEVEL: str = Field("INFO", description="Logging level")
    INTERVAL_SECONDS: int = Field(60, description="Alert check interval in seconds")
    LOOKBACK_MINUTES: int = Field(10, description="Lookback window for recent KPIs")
    CURRENT_WINDOW_MINUTES: int = Field(
        5, description="Smoothing window for current KPI"
    )
    DURATION_MINUTES: int = Field(3, description="Minutes the deviation must persist")

    DB_DSN: str = Field(..., description="PostgreSQL DSN")

    BASELINE_DAYS: int = Field(7, description="Baseline days for comparisons")
    REVENUE_UP_THRESHOLD_PCT: float = Field(
        1.0,
        description="Alert threshold percentage for upward revenue deviations",
    )
    REVENUE_DOWN_THRESHOLD_PCT: float = Field(
        0.5,
        description="Alert threshold percentage for downward revenue deviations",
    )
    VIEW_UP_THRESHOLD_PCT: float = Field(
        0.5,
        description="Alert threshold percentage for upward view_count deviations",
    )
    VIEW_DOWN_THRESHOLD_PCT: float = Field(
        0.4,
        description="Alert threshold percentage for downward view_count deviations",
    )
    MIN_BASELINE: float = Field(10, description="Minimum baseline value")


dynaconf_settings = Dynaconf(
    envvar_prefix="ALERTING",
    environments=True,
    settings_files=[BASE_DIR / "settings.toml", BASE_DIR / ".secrets.toml"],
    root_path=BASE_DIR,
    load_dotenv=False,
)


@lru_cache
def get_settings() -> Settings:
    return Settings(**dynaconf_settings)  # type: ignore[arg-type]
