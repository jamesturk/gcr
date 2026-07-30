import dacite
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    staff_team: str = "staff"
    student_permission: str = "push"
    staff_permission: str = "maintain"
    requests_per_minute: int = 60
    retry_attempts: int = 3
    retry_wait_seconds: float = 5.0


@dataclass(frozen=True)
class Config:
    org: str
    students: list[str]
    staff: list[str] = field(default_factory=list)
    settings: Settings = field(default_factory=Settings)


def load_config(path: Path) -> Config:
    # let exceptions propagate, will be shown in UI
    data = tomllib.loads(path.read_text())
    # strict, flag unknown keys; cast floats/ints
    return dacite.from_dict(
        Config, data, config=dacite.Config(strict=True, cast=[float])
    )
