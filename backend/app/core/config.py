from functools import lru_cache

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ScoreWeights(BaseModel):
    """Configurable Rotation Score weights. Must sum to 1.0."""

    flow: float = 0.30
    acceleration: float = 0.25
    price_momentum: float = 0.15
    volume_expansion: float = 0.15
    continuity: float = 0.10
    margin: float = 0.05

    @model_validator(mode="after")
    def weights_must_sum_to_one(self) -> "ScoreWeights":
        total = (
            self.flow
            + self.acceleration
            + self.price_momentum
            + self.volume_expansion
            + self.continuity
            + self.margin
        )
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"Score weights must sum to 1.0, got {total}")
        return self

    def as_dict(self) -> dict[str, float]:
        return {
            "normalized_flow": self.flow,
            "acceleration": self.acceleration,
            "price_momentum": self.price_momentum,
            "volume_expansion": self.volume_expansion,
            "continuity": self.continuity,
            "margin_signal": self.margin,
        }


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./data/radar.db"
    http_timeout_seconds: float = 20.0
    http_max_retries: int = 3
    http_retry_backoff_seconds: float = 0.5
    twse_base_url: str = "https://www.twse.com.tw"
    tpex_base_url: str = "https://www.tpex.org.tw"
    twse_openapi_url: str = "https://openapi.twse.com.tw"

    weight_flow: float = Field(default=0.30)
    weight_acceleration: float = Field(default=0.25)
    weight_price_momentum: float = Field(default=0.15)
    weight_volume_expansion: float = Field(default=0.15)
    weight_continuity: float = Field(default=0.10)
    weight_margin: float = Field(default=0.05)
    min_coverage_ratio: float = Field(default=0.80)

    @property
    def score_weights(self) -> ScoreWeights:
        return ScoreWeights(
            flow=self.weight_flow,
            acceleration=self.weight_acceleration,
            price_momentum=self.weight_price_momentum,
            volume_expansion=self.weight_volume_expansion,
            continuity=self.weight_continuity,
            margin=self.weight_margin,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
