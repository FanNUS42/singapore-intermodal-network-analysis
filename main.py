from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Literal

from config import CONFIG
from scripts.common.io_utils import (
    deep_merge,
    project_root_from,
    scenario_names_from,
)

StageScope = Literal["shared", "scenario", "comparison"]

STAGE_SCRIPTS: Dict[str, tuple[StageScope, str]] = {
    "build_bus_base": ("shared", "scripts/raw/build_bus_base.py"),
    "build_mrt_base": ("shared", "scripts/raw/build_mrt_base.py"),
    "build_scenario_mrt_base": ("scenario", "scripts/scenario/build_scenario_mrt_base.py"),
    "build_mrt_station_centrality": ("scenario", "scripts/analysis/build_mrt_station_centrality.py"),
    "build_intermodal_base": ("scenario", "scripts/intermodal/build_intermodal_base.py"),
    "build_terminal_sets": ("scenario", "scripts/scenario/build_terminal_sets.py"),
    "build_nodes_from_base": ("scenario", "scripts/graph/build_nodes_from_base.py"),
    "build_links_from_base": ("scenario", "scripts/graph/build_links_from_base.py"),
    "build_od_shortest_paths": ("scenario", "scripts/analysis/build_od_shortest_paths.py"),
    "compare_mrt_station_centrality": ("comparison", "scripts/analysis/compare_mrt_station_centrality.py"),
    "compare_od_shortest_paths": ("comparison", "scripts/analysis/compare_od_shortest_paths.py"),
    "build_path_restructuring_analysis": ("comparison", "scripts/analysis/build_path_restructuring_analysis.py"),
    "build_network_incidence_delta": ("comparison", "scripts/analysis/build_network_incidence_delta.py"),
    "build_summary_4_3": ("comparison", "scripts/analysis/build_summary_4_3.py"),
    "build_origin_impact_payload": ("comparison", "scripts/analysis/build_origin_impact_payload.py"),
    "build_origin_spatial_visualization": ("comparison", "scripts/analysis/build_origin_spatial_visualization.py"),
    "build_origin_impact_dashboard": ("comparison", "scripts/analysis/build_origin_impact_dashboard.py"),
    "write_run_metadata": ("comparison", "scripts/analysis/write_run_metadata.py"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the intermodal build pipeline")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--scenario", type=str, default="all", choices=["all", *scenario_names_from(CONFIG)])
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--skip", nargs="*", default=[])
    parser.add_argument(
        "--in-process",
        action="store_true",
        help="Reserved for debugging. The default subprocess mode is recommended for long full-pipeline runs.",
    )
    return parser.parse_args()


def _stage_selected(stage: str, only: set[str], skip: set[str]) -> bool:
    if only and stage not in only:
        return False
    if stage in skip:
        return False
    return True


def _validate_stage_names(cfg: dict, requested_stages: set[str]) -> None:
    known = set(STAGE_SCRIPTS)
    configured = set(cfg.get("shared_stage_order", [])) | set(cfg.get("scenario_stage_order", [])) | set(cfg.get("comparison_stage_order", []))
    unknown = (requested_stages | configured) - known
    if unknown:
        raise KeyError(f"Unknown stage name(s): {', '.join(sorted(unknown))}")


def _run_stage(
    stage: str,
    cfg: dict,
    root: Path,
    scenario_name: str | None = None,
    comparison_scenarios: list[str] | None = None,
) -> None:
    if not cfg["switches"].get(stage, True):
        print(f"[SKIP] {stage}", flush=True)
        return
    scope, script_rel = STAGE_SCRIPTS[stage]
    script_path = root / script_rel
    if not script_path.exists():
        raise FileNotFoundError(f"Stage script not found: {script_path}")

    cmd = [sys.executable, str(script_path), "--project-root", str(root)]
    if scope == "scenario":
        if scenario_name is None:
            raise ValueError(f"Stage {stage} requires a scenario name")
        cmd.extend(["--scenario", scenario_name])
    elif scope == "comparison" and comparison_scenarios is not None and len(comparison_scenarios) >= 2:
        if stage in {
            "compare_mrt_station_centrality",
            "compare_od_shortest_paths",
            "build_path_restructuring_analysis",
            "build_network_incidence_delta",
        }:
            cmd.extend(["--pre", comparison_scenarios[0], "--post", comparison_scenarios[1]])

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(root) if not existing_pythonpath else f"{root}{os.pathsep}{existing_pythonpath}"
    print(f"[RUN ] {stage}", flush=True)
    subprocess.run(cmd, cwd=str(root), env=env, check=True)


def main() -> None:
    args = parse_args()
    cfg = deep_merge(CONFIG, {})
    root = project_root_from(cfg, args.project_root)
    only = set(args.only)
    skip = set(args.skip)
    _validate_stage_names(cfg, only | skip)
    requested_scenarios = scenario_names_from(cfg) if args.scenario == "all" else [args.scenario]

    for stage in cfg["shared_stage_order"]:
        if _stage_selected(stage, only, skip):
            _run_stage(stage, cfg, root)

    for scenario_name in requested_scenarios:
        print(f"[SCENARIO] {scenario_name}", flush=True)
        for stage in cfg["scenario_stage_order"]:
            if _stage_selected(stage, only, skip):
                _run_stage(stage, cfg, root, scenario_name=scenario_name)

    if len(requested_scenarios) >= 2:
        for stage in cfg.get("comparison_stage_order", []):
            if _stage_selected(stage, only, skip):
                _run_stage(stage, cfg, root, comparison_scenarios=requested_scenarios)

    print("done", flush=True)


if __name__ == "__main__":
    main()
