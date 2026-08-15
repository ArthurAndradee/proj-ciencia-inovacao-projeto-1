"""Experiment configuration, loaded from environment variables / .env."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


REPO_ROOT: Path = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Config:
    """Every knob of the experiment, resolved once and passed around read-only."""

    api_key: str
    generator_model: str
    critic_model: str
    split: str
    sample_size: int
    seed: int
    budget_calls: int
    temperature: float
    max_output_tokens: int
    rpm: int
    max_retries: int
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
            api_key=os.getenv("GOOGLE_API_KEY", ""),
            generator_model=os.getenv("GENERATOR_MODEL", "gemini-3.7-flash"),
            critic_model=os.getenv("CRITIC_MODEL", "gemini-3.7-flash"),
            split=os.getenv("ARC_SPLIT", "evaluation"),
            sample_size=int(os.getenv("SAMPLE_SIZE", "100")),
            seed=int(os.getenv("SEED", "20260814")),
            budget_calls=int(os.getenv("BUDGET_CALLS", "12")),
            temperature=float(os.getenv("TEMPERATURE", "0.2")),
            max_output_tokens=int(os.getenv("MAX_OUTPUT_TOKENS", "8192")),
            rpm=int(os.getenv("RPM", "0")),
            max_retries=int(os.getenv("MAX_RETRIES", "5")),
            exec_timeout_s=float(os.getenv("EXEC_TIMEOUT_S", "10")),
            exec_memory_mb=int(os.getenv("EXEC_MEMORY_MB", "1024")),
            data_dir=path_of("DATA_DIR", "data"),
            results_dir=path_of("RESULTS_DIR", "results"),
        )

    def manifest(self) -> dict[str, Any]:
        """Serializable view of the configuration, with the API key stripped."""
        data: dict[str, Any] = {
            key: (str(value) if isinstance(value, Path) else value)
            for key, value in asdict(self).items()
        }
        data.pop("api_key")
        return data
