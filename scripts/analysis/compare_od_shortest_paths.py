from __future__ import annotations

import argparse
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Tuple

PATH_FIELDS = ("path_node_ids", "path_link_ids")

from config import CONFIG
from scripts.common.io_utils import load_json, project_root_from, resolve_path, runtime_cfg_for_comparison, save_json


def _record_index(payload: Dict[str, Any]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    out: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for record in payload.get("records", []):
        key = (str(record["source_id"]), str(record["sink_set"]), str(record["sink_id"]))
        out[key] = record
    return out


def compare_od_shortest_paths(cfg: Dict[str, Any], project_root: Path) -> Dict[str, Any]:
    runtime = cfg.get("_runtime", {})
    scenario_names = runtime.get("comparison_scenarios") or ["pre_ring", "post_ring"]
    if len(scenario_names) != 2:
        raise ValueError("compare_od_shortest_paths expects exactly two scenarios")
    pre_name, post_name = scenario_names
    analysis_cfg = cfg["paths"]["analysis"]["scenario"]
    pre_path = resolve_path(project_root, analysis_cfg[pre_name]["od_shortest_paths_json"])
    post_path = resolve_path(project_root, analysis_cfg[post_name]["od_shortest_paths_json"])
    out_path = resolve_path(project_root, cfg["paths"]["analysis"]["comparison"]["od_shortest_paths_json"])

    pre_payload = load_json(pre_path)
    post_payload = load_json(post_path)
    pre_index = _record_index(pre_payload)
    post_index = _record_index(post_payload)
    all_keys = sorted(set(pre_index) | set(post_index))

    records: List[Dict[str, Any]] = []
    deltas_common: List[float] = []
    improved = 0
    worsened = 0
    unchanged = 0
    newly_reachable = 0
    no_longer_reachable = 0
    for key in all_keys:
        pre = pre_index.get(key)
        post = post_index.get(key)
        source_id, sink_set, sink_id = key
        pre_reachable = bool(pre and pre.get("reachable"))
        post_reachable = bool(post and post.get("reachable"))
        source_name = (pre or post or {}).get("source_name")
        sink_name = (pre or post or {}).get("sink_name")
        pre_time = pre.get("time_min") if pre else None
        post_time = post.get("time_min") if post else None
        delta_time = None
        change_type = "missing"
        if pre_reachable and post_reachable and pre_time is not None and post_time is not None:
            delta_time = round(float(post_time) - float(pre_time), 3)
            deltas_common.append(delta_time)
            if delta_time < 0:
                change_type = "improved"
                improved += 1
            elif delta_time > 0:
                change_type = "worsened"
                worsened += 1
            else:
                change_type = "unchanged"
                unchanged += 1
        elif (not pre_reachable) and post_reachable:
            change_type = "newly_reachable"
            newly_reachable += 1
        elif pre_reachable and (not post_reachable):
            change_type = "no_longer_reachable"
            no_longer_reachable += 1
        elif (not pre_reachable) and (not post_reachable):
            change_type = "both_unreachable"
        pre_path_node_ids = pre.get("path_node_ids") if pre else []
        post_path_node_ids = post.get("path_node_ids") if post else []
        pre_path_link_ids = pre.get("path_link_ids") if pre else []
        post_path_link_ids = post.get("path_link_ids") if post else []
        path_changed = (
            pre_reachable != post_reachable
            or pre_path_node_ids != post_path_node_ids
            or pre_path_link_ids != post_path_link_ids
        )
        time_changed = None if delta_time is None else bool(float(delta_time) != 0.0)
        records.append({
            "source_id": source_id,
            "source_name": source_name,
            "sink_set": sink_set,
            "sink_id": sink_id,
            "sink_name": sink_name,
            "pre_reachable": pre_reachable,
            "post_reachable": post_reachable,
            "pre_time_min": pre_time,
            "post_time_min": post_time,
            "delta_time_min": delta_time,
            "change_type": change_type,
            "path_changed": path_changed,
            "time_changed": time_changed,
            "pre_path_node_ids": pre_path_node_ids,
            "post_path_node_ids": post_path_node_ids,
            "pre_path_link_ids": pre_path_link_ids,
            "post_path_link_ids": post_path_link_ids,
            "pre_path_time_breakdown": pre.get("path_time_breakdown") if pre else {},
            "post_path_time_breakdown": post.get("path_time_breakdown") if post else {},
        })

    top_improvements = sorted([r for r in records if r["change_type"] == "improved"], key=lambda r: (r["delta_time_min"], r["source_id"], r["sink_set"], r["sink_id"]))[:20]
    top_worsenings = sorted([r for r in records if r["change_type"] == "worsened"], key=lambda r: (-r["delta_time_min"], r["source_id"], r["sink_set"], r["sink_id"]))[:20]

    payload = {
        "meta": {
            "comparison": [pre_name, post_name],
            "input_files": {
                pre_name: str(pre_path.relative_to(project_root)),
                post_name: str(post_path.relative_to(project_root)),
            },
            "record_count": len(records),
        },
        "summary": {
            "common_reachable_pair_count": len(deltas_common),
            "avg_delta_time_min": round(mean(deltas_common), 3) if deltas_common else None,
            "improved_count": improved,
            "worsened_count": worsened,
            "unchanged_count": unchanged,
            "newly_reachable_count": newly_reachable,
            "no_longer_reachable_count": no_longer_reachable,
            "path_changed_count": sum(1 for r in records if r.get("path_changed")),
            "time_changed_count": sum(1 for r in records if r.get("time_changed") is True),
        },
        "top_improvements": top_improvements,
        "top_worsenings": top_worsenings,
        "records": records,
    }
    save_json(out_path, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare OD shortest path results between two scenarios")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--pre", type=str, default="pre_ring")
    parser.add_argument("--post", type=str, default="post_ring")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg = runtime_cfg_for_comparison(CONFIG, [args.pre, args.post])
    root = project_root_from(cfg, args.project_root)
    compare_od_shortest_paths(cfg, root)
