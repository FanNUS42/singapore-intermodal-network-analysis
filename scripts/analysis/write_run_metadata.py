from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

from config import CONFIG
from scripts.common.io_utils import project_root_from, resolve_path, runtime_cfg_for_comparison, save_json


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _file_info(project_root: Path, rel_path: str) -> Dict[str, Any]:
    path = resolve_path(project_root, rel_path)
    info: Dict[str, Any] = {
        "path": rel_path,
        "exists": path.exists(),
    }
    if path.exists() and path.is_file():
        stat = path.stat()
        info.update({
            "size_bytes": stat.st_size,
            "modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "sha256": _sha256(path),
        })
    return info


def _configured_outputs(cfg: Dict[str, Any]) -> Iterable[str]:
    for rel in cfg.get("paths", {}).get("model", {}).get("base", {}).values():
        yield str(rel)
    for scenario_paths in cfg.get("paths", {}).get("model", {}).get("scenario", {}).values():
        for rel in scenario_paths.values():
            yield str(rel)
    for scenario_paths in cfg.get("paths", {}).get("analysis", {}).get("scenario", {}).values():
        for rel in scenario_paths.values():
            yield str(rel)
    comparison = cfg.get("paths", {}).get("analysis", {}).get("comparison", {})
    for key, value in comparison.items():
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for rel in value.values():
                yield str(rel)
    for section in ["origin_impact", "visualization"]:
        for rel in cfg.get("paths", {}).get("analysis", {}).get(section, {}).values():
            yield str(rel)


def write_run_metadata(cfg: Dict[str, Any], project_root: Path) -> Dict[str, Any]:
    out_path = resolve_path(project_root, cfg["paths"]["analysis"].get("run_metadata_json", "analysis/run_metadata.json"))
    output_paths = sorted(set(_configured_outputs(cfg)))
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "python": {
            "version": sys.version,
            "executable": sys.executable,
            "implementation": platform.python_implementation(),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "project_root": str(project_root),
        "scenarios": cfg.get("scenario_order", []),
        "stage_order": {
            "shared": cfg.get("shared_stage_order", []),
            "scenario": cfg.get("scenario_stage_order", []),
            "comparison": cfg.get("comparison_stage_order", []),
        },
        "key_parameters": cfg.get("params", {}),
        "outputs": [_file_info(project_root, rel) for rel in output_paths],
    }
    save_json(out_path, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write run metadata for generated model and analysis outputs")
    parser.add_argument("--project-root", type=Path, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg = runtime_cfg_for_comparison(CONFIG, ["pre_ring", "post_ring"])
    root = project_root_from(cfg, args.project_root)
    print(json.dumps(write_run_metadata(cfg, root), ensure_ascii=False, indent=2))
