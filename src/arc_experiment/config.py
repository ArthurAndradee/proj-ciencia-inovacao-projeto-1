"""Experiment configuration, loaded from environment variables / .env."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


REPO_ROOT: Path = Path(__file__).resolve().parents[2]


def parse_api_keys(joined: str) -> tuple[str, ...]:
    """Comma-separated keys, in order, without blanks or repeats.

    Order matters: it is the order the pool falls back through, and the labels
    reported at the end of a run refer to it. Duplicates are dropped because two
    entries of the same key would look like twice the quota and deliver once.
    """
    keys: list[str] = []
    for raw in joined.split(","):
        key: str = raw.strip()
        if key and key not in keys:
            keys.append(key)
    return tuple(keys)


@dataclass(frozen=True)
class Config:
    """Every knob of the experiment, resolved once and passed around read-only."""

    api_keys: tuple[str, ...]
    generator_model: str
    critic_model: str
    split: str
    sample_size: int
    seed: int
    budget_calls: int
    temperature: float
    sampling_temperature: float
    max_output_tokens: int
    rpm: int
    max_retries: int
    request_timeout_s: float
    exec_timeout_s: float
    exec_memory_mb: int
    data_dir: Path
    results_dir: Path

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> Config:
        load_dotenv(env_file or REPO_ROOT / ".env")

        def path_of(key: str, default: str) -> Path:
            raw = Path(os.getenv(key, default))
            return raw if raw.is_absolute() else REPO_ROOT / raw

        return cls(
            api_keys=parse_api_keys(
                os.getenv("GOOGLE_API_KEYS", "") or os.getenv("GOOGLE_API_KEY", "")
            ),
            generator_model=os.getenv("GENERATOR_MODEL", "gemini-3.7-flash"),
            critic_model=os.getenv("CRITIC_MODEL", "gemini-3.7-flash"),
            split=os.getenv("ARC_SPLIT", "evaluation"),
            sample_size=int(os.getenv("SAMPLE_SIZE", "100")),
            seed=int(os.getenv("SEED", "20260814")),
            budget_calls=int(os.getenv("BUDGET_CALLS", "12")),
            temperature=float(os.getenv("TEMPERATURE", "0.2")),
            sampling_temperature=float(os.getenv("SAMPLING_TEMPERATURE", "0.8")),
            max_output_tokens=int(os.getenv("MAX_OUTPUT_TOKENS", "8192")),
            rpm=int(os.getenv("RPM", "0")),
            max_retries=int(os.getenv("MAX_RETRIES", "5")),
            request_timeout_s=float(os.getenv("REQUEST_TIMEOUT_S", "180")),
            exec_timeout_s=float(os.getenv("EXEC_TIMEOUT_S", "10")),
            exec_memory_mb=int(os.getenv("EXEC_MEMORY_MB", "1024")),
            data_dir=path_of("DATA_DIR", "data"),
            results_dir=path_of("RESULTS_DIR", "results"),
        )

    def manifest(self) -> dict[str, Any]:
        """Serializable view of the configuration, with the API keys stripped.

        The count stays: how many quotas a run had access to explains its pace
        and where it stopped, and it cannot be recovered from the results later.
        """
        data: dict[str, Any] = {
            key: (str(value) if isinstance(value, Path) else value)
            for key, value in asdict(self).items()
        }
        data.pop("api_keys")
        data["key_count"] = len(self.api_keys)
        return data
