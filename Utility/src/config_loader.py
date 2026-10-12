from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_app_config(config_path: Path) -> Dict[str, Any]:
    config = load_json(config_path)
    config["config_path"] = str(config_path)
    config["base_dir"] = str(config_path.parent.parent)
    return config
