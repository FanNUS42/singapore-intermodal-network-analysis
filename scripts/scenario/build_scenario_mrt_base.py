from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Any, Dict

from config import CONFIG
from scripts.common.io_utils import (
    get_active_scenario,
    get_scenario_definition,
    get_scenario_model_paths,
    load_json,
    path_to_rel_or_abs,
    project_root_from,
    resolve_path,
    save_json,
)
from scripts.scenario.apply_cc_ring_overlay import (
    annotate_cc_ring_meta,
    apply_cc_ring_overlay_to_payload,
    load_closing_links,
    load_new_stations,
)


def _annotate_baseline_meta(payload: Dict[str, Any], source_rel: str, scenario_name: str, description: str) -> Dict[str, Any]:
    out = copy.deepcopy(payload)
    meta = out.setdefault("meta", {})
    source_files = meta.setdefault("source_files", {})
    source_files["base_mrt_base_json"] = source_rel
    meta["scenario"] = {
        "scenario_name": scenario_name,
        "mrt_strategy": "baseline_copy",
        "description": description,
    }
    meta["counts"] = {
        "platform_nodes": len(out.get("platform_nodes", [])),
        "station_hubs": len(out.get("station_hubs", [])),
        "run_links": len(out.get("run_links", [])),
    }
    return out


def build_scenario_mrt_base(cfg: Dict[str, Any], project_root: Path) -> Dict[str, Any]:
    scenario_name = get_active_scenario(cfg)
    scenario_def = get_scenario_definition(cfg, scenario_name)
    out_path = resolve_path(project_root, get_scenario_model_paths(cfg, scenario_name)["mrt_base_json"])
    base_in = resolve_path(project_root, cfg["paths"]["model"]["base"]["mrt_base_json"])
    base_payload = load_json(base_in)

    strategy = str(scenario_def.get("mrt_strategy", "baseline_copy"))
    description = str(scenario_def.get("description", scenario_name))

    if strategy == "baseline_copy":
        payload = _annotate_baseline_meta(base_payload, path_to_rel_or_abs(project_root, base_in), scenario_name, description)
        save_json(out_path, payload)
        return payload

    if strategy == "cc_ring_overlay":
        overlay_key = str(scenario_def.get("overlay_key", "cc_ring"))
        raw_scenario = cfg["paths"]["raw"]["scenario"][overlay_key]
        station_path = resolve_path(project_root, raw_scenario["new_mrt_stations_geojson"])
        links_path = resolve_path(project_root, raw_scenario["cc_ring_links_json"])
        new_stations = load_new_stations(station_path)
        closing_links = load_closing_links(links_path)
        payload = apply_cc_ring_overlay_to_payload(
            base_payload,
            new_stations,
            closing_links,
        )
        payload = annotate_cc_ring_meta(
            payload,
            path_to_rel_or_abs(project_root, station_path),
            path_to_rel_or_abs(project_root, links_path),
            new_stations=new_stations,
            closing_links=closing_links,
            scenario_name=scenario_name,
        )
        save_json(out_path, payload)
        return payload

    raise ValueError(f"Unsupported mrt_strategy {strategy!r} for scenario {scenario_name!r}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build scenario-specific MRT base JSON")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--scenario", type=str, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg = copy.deepcopy(CONFIG)
    cfg.setdefault("_runtime", {})["active_scenario"] = args.scenario
    root = project_root_from(cfg, args.project_root)
    build_scenario_mrt_base(cfg, root)
