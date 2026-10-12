"""Проверяемая конфигурация алгоритмов; денежные и сетевые сервисы не используются."""
from dataclasses import dataclass, asdict
import json
from pathlib import Path


@dataclass(frozen=True)
class Config:
    horizon_days: int = 7
    weekday_mean_weeks: int = 4
    backtest_folds: int = 3
    backtest_days: int = 7
    min_training_days: int = 14
    min_eval_points: int = 7
    fallback_observations: int = 7
    safety_pct: float = 0.15
    max_plan_days: int = 60

    def __post_init__(self):
        for key, value in asdict(self).items():
            if key != "safety_pct" and (type(value) is not int or value <= 0):
                raise ValueError(f"{key}: требуется положительное целое число")
        if not 0 <= self.safety_pct <= 1:
            raise ValueError("safety_pct: требуется доля от 0 до 1")
        if self.max_plan_days < self.horizon_days:
            raise ValueError("max_plan_days должен быть не меньше horizon_days")

    @classmethod
    def load(cls, path: str | Path | None = None):
        return cls(**json.loads(Path(path).read_text(encoding="utf-8"))) if path else cls()
