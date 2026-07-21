"""Optional user-level model configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .errors import invalid


DEFAULT_MODELS = {
    "opening": "gpt-5.4-mini",
    "search": "gpt-5.6-sol",
    "synthesis": "gpt-5.6-sol",
}


def model_name(stage: str) -> str:
    if stage not in DEFAULT_MODELS:
        raise ValueError(f"unsupported model stage: {stage}")
    environment = os.environ.get(f"RESEARCH_REACH_{stage.upper()}_MODEL")
    if environment and environment.strip():
        return environment.strip()
    configured = os.environ.get("RESEARCH_REACH_CONFIG")
    path = Path(configured).expanduser() if configured else Path.home() / ".research-reach" / "models.json"
    if not path.is_file():
        return DEFAULT_MODELS[stage]
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise invalid(f"model config is not valid JSON: {path}") from exc
    key = f"{stage}_model"
    model = value.get(key) if isinstance(value, dict) else None
    if not isinstance(model, str) or not model.strip():
        raise invalid(f"model config requires a non-empty {key}")
    return model.strip()
