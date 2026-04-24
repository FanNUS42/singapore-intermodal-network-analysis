from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
from typing import Any, Dict, List


def project_root_from(cfg: Dict[str, Any], override: str | Path | None = None) -> Path:
    if override is not None:
        return Path(override).resolve()
    return Path(__file__).resolve().parents[2]


def resolve_path(project_root: Path, rel_or_abs: str) -> Path:
    p = Path(rel_or_abs)
    return p if p.is_absolute() else project_root / p


def path_to_rel_or_abs(project_root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def save_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    fieldnames: List[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key in seen:
                continue
            seen.add(key)
            fieldnames.append(str(key))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def scenario_names_from(cfg: Dict[str, Any]) -> List[str]:
    names = cfg.get("scenario_order")
    if names:
        return [str(x) for x in names]
    return [str(x) for x in cfg.get("scenarios", {}).keys()]


def get_active_scenario(cfg: Dict[str, Any]) -> str:
    runtime = cfg.get("_runtime", {})
    name = runtime.get("active_scenario")
    if not name:
        raise ValueError("No active scenario is set in cfg['_runtime']['active_scenario']")
    return str(name)


def get_scenario_definition(cfg: Dict[str, Any], scenario_name: str | None = None) -> Dict[str, Any]:
    name = scenario_name or get_active_scenario(cfg)
    scenarios = cfg.get("scenarios", {})
    if name not in scenarios:
        raise KeyError(f"Scenario {name!r} is not defined in config")
    return scenarios[name]


def get_scenario_model_paths(cfg: Dict[str, Any], scenario_name: str | None = None) -> Dict[str, str]:
    name = scenario_name or get_active_scenario(cfg)
    model_paths = cfg.get("paths", {}).get("model", {}).get("scenario", {})
    if name not in model_paths:
        raise KeyError(f"Scenario model paths for {name!r} are not defined in config")
    return model_paths[name]


def get_scenario_analysis_paths(cfg: Dict[str, Any], scenario_name: str | None = None) -> Dict[str, str]:
    name = scenario_name or get_active_scenario(cfg)
    analysis_paths = cfg.get("paths", {}).get("analysis", {}).get("scenario", {})
    if name not in analysis_paths:
        raise KeyError(f"Scenario analysis paths for {name!r} are not defined in config")
    return analysis_paths[name]


def runtime_cfg_for_scenario(cfg: Dict[str, Any], scenario_name: str) -> Dict[str, Any]:
    out = copy.deepcopy(cfg)
    out.setdefault("_runtime", {})["active_scenario"] = str(scenario_name)
    return out


def runtime_cfg_for_comparison(cfg: Dict[str, Any], scenario_names: List[str]) -> Dict[str, Any]:
    out = copy.deepcopy(cfg)
    out.setdefault("_runtime", {})["comparison_scenarios"] = [str(x) for x in scenario_names]
    return out
