from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from config import CONFIG
from scripts.analysis.path_analysis_utils import (
    counter_to_sorted_list,
    load_links_lookup,
    load_nodes_lookup,
    load_ring_overlay_info,
    path_bus_services_used,
    path_lines_used,
    path_modes_used,
    path_mrt_station_sequence,
    path_run_link_sequence,
    path_transfer_count,
    ring_usage_info,
)
from scripts.common.io_utils import load_json, project_root_from, resolve_path, runtime_cfg_for_comparison, save_json


def _paths_changed(record: Dict[str, Any]) -> bool:
    return bool(record.get("path_changed"))


def _links_added_removed(pre_link_ids: List[str], post_link_ids: List[str]) -> Dict[str, List[str]]:
    pre_set = set(pre_link_ids)
    post_set = set(post_link_ids)
    return {
        "added_link_ids": [x for x in post_link_ids if x not in pre_set],
        "removed_link_ids": [x for x in pre_link_ids if x not in post_set],
    }


def _station_codes(sequence: List[Dict[str, Any]]) -> List[str]:
    return [str(x.get("station_code")) for x in sequence if x.get("station_code")]


def build_path_restructuring_analysis(cfg: Dict[str, Any], project_root: Path) -> Dict[str, Any]:
    runtime = cfg.get("_runtime", {})
    scenario_names = runtime.get("comparison_scenarios") or ["pre_ring", "post_ring"]
    if len(scenario_names) != 2:
        raise ValueError("build_path_restructuring_analysis expects exactly two scenarios")
    pre_name, post_name = scenario_names

    compare_path = resolve_path(project_root, cfg["paths"]["analysis"]["comparison"]["od_shortest_paths_json"])
    pre_nodes_path = resolve_path(project_root, cfg["paths"]["model"]["scenario"][pre_name]["nodes_json"])
    pre_links_path = resolve_path(project_root, cfg["paths"]["model"]["scenario"][pre_name]["links_json"])
    post_nodes_path = resolve_path(project_root, cfg["paths"]["model"]["scenario"][post_name]["nodes_json"])
    post_links_path = resolve_path(project_root, cfg["paths"]["model"]["scenario"][post_name]["links_json"])
    out_paths = cfg["paths"]["analysis"]["comparison"]["path_restructuring"]
    out_json_path = resolve_path(project_root, out_paths["od_records_json"])
    out_summary_path = resolve_path(project_root, out_paths["summary_json"])

    compare_payload = load_json(compare_path)
    pre_nodes = load_nodes_lookup(pre_nodes_path)
    pre_links = load_links_lookup(pre_links_path)
    post_nodes = load_nodes_lookup(post_nodes_path)
    post_links = load_links_lookup(post_links_path)
    ring_info = load_ring_overlay_info(cfg, project_root, post_name)

    pattern_counter: Counter[str] = Counter()
    records: List[Dict[str, Any]] = []
    changed_count = 0
    changed_improved = 0
    changed_equal_time = 0
    changed_worsened = 0
    changed_use_new_ring = 0
    changed_full_ring = 0

    for record in compare_payload.get("records", []):
        pre_path_link_ids = list(record.get("pre_path_link_ids") or [])
        post_path_link_ids = list(record.get("post_path_link_ids") or [])
        pre_path_node_ids = list(record.get("pre_path_node_ids") or [])
        post_path_node_ids = list(record.get("post_path_node_ids") or [])
        pre_mrt_seq = path_mrt_station_sequence(pre_path_link_ids, pre_links)
        post_mrt_seq = path_mrt_station_sequence(post_path_link_ids, post_links)
        pre_bus_services = path_bus_services_used(pre_path_link_ids, pre_links)
        post_bus_services = path_bus_services_used(post_path_link_ids, post_links)
        pre_mrt_lines = path_lines_used(pre_path_link_ids, pre_links)
        post_mrt_lines = path_lines_used(post_path_link_ids, post_links)
        pre_modes = path_modes_used(pre_path_link_ids, pre_links)
        post_modes = path_modes_used(post_path_link_ids, post_links)
        pre_transfer_count = path_transfer_count(pre_path_link_ids, pre_links)
        post_transfer_count = path_transfer_count(post_path_link_ids, post_links)
        ring_usage = ring_usage_info(post_path_link_ids, ring_info)
        delta_time = record.get("delta_time_min")
        path_changed = _paths_changed(record)
        link_delta = _links_added_removed(pre_path_link_ids, post_path_link_ids)
        pre_station_codes = _station_codes(pre_mrt_seq)
        post_station_codes = _station_codes(post_mrt_seq)

        enriched = {
            "source_id": record.get("source_id"),
            "source_name": record.get("source_name"),
            "sink_set": record.get("sink_set"),
            "sink_id": record.get("sink_id"),
            "sink_name": record.get("sink_name"),
            "pre_reachable": record.get("pre_reachable"),
            "post_reachable": record.get("post_reachable"),
            "pre_time_min": record.get("pre_time_min"),
            "post_time_min": record.get("post_time_min"),
            "delta_time_min": delta_time,
            "change_type": record.get("change_type"),
            "path_changed": path_changed,
            "time_changed": record.get("time_changed"),
            "pre_transfer_count": pre_transfer_count,
            "post_transfer_count": post_transfer_count,
            "transfer_count_delta": post_transfer_count - pre_transfer_count,
            "pre_modes_used": pre_modes,
            "post_modes_used": post_modes,
            "pre_bus_services_used": pre_bus_services,
            "post_bus_services_used": post_bus_services,
            "pre_mrt_lines_used": pre_mrt_lines,
            "post_mrt_lines_used": post_mrt_lines,
            "pre_mrt_station_sequence": pre_mrt_seq,
            "post_mrt_station_sequence": post_mrt_seq,
            "pre_mrt_station_codes": pre_station_codes,
            "post_mrt_station_codes": post_station_codes,
            "pre_run_link_sequence": path_run_link_sequence(pre_path_link_ids, pre_links),
            "post_run_link_sequence": path_run_link_sequence(post_path_link_ids, post_links),
            **ring_usage,
            **link_delta,
            "pre_path_node_ids": pre_path_node_ids,
            "post_path_node_ids": post_path_node_ids,
            "pre_path_link_ids": pre_path_link_ids,
            "post_path_link_ids": post_path_link_ids,
        }
        records.append(enriched)

        if path_changed:
            changed_count += 1
            if delta_time is not None and float(delta_time) < 0:
                changed_improved += 1
            elif delta_time is not None and float(delta_time) > 0:
                changed_worsened += 1
            else:
                changed_equal_time += 1
            if ring_usage["uses_new_ring"]:
                changed_use_new_ring += 1
            if ring_usage["new_ring_is_full_traversal"]:
                changed_full_ring += 1
            pattern_counter[ring_usage["ring_usage_pattern"]] += 1

    summary = {
        "comparison": [pre_name, post_name],
        "record_count": len(records),
        "path_changed_count": changed_count,
        "path_changed_share": round(changed_count / len(records), 6) if records else None,
        "path_changed_improved_count": changed_improved,
        "path_changed_equal_time_count": changed_equal_time,
        "path_changed_worsened_count": changed_worsened,
        "changed_using_new_ring_count": changed_use_new_ring,
        "changed_using_new_ring_share": round(changed_use_new_ring / changed_count, 6) if changed_count else None,
        "changed_full_ring_traversal_count": changed_full_ring,
        "changed_partial_ring_usage_count": changed_use_new_ring - changed_full_ring,
        "changed_ring_usage_pattern_counts": counter_to_sorted_list(pattern_counter),
        "ring_overlay": ring_info,
    }

    payload = {
        "meta": {
            "comparison": [pre_name, post_name],
            "input_compare_file": str(compare_path.relative_to(project_root)),
            "input_lookup_files": {
                pre_name: {
                    "nodes_json": str(pre_nodes_path.relative_to(project_root)),
                    "links_json": str(pre_links_path.relative_to(project_root)),
                },
                post_name: {
                    "nodes_json": str(post_nodes_path.relative_to(project_root)),
                    "links_json": str(post_links_path.relative_to(project_root)),
                },
            },
        },
        "summary": summary,
        "records": records,
    }
    save_json(out_json_path, payload)
    save_json(out_summary_path, summary)
    return payload



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build OD path restructuring analysis for a scenario comparison")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--pre", type=str, default="pre_ring")
    parser.add_argument("--post", type=str, default="post_ring")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg = runtime_cfg_for_comparison(CONFIG, [args.pre, args.post])
    root = project_root_from(cfg, args.project_root)
    build_path_restructuring_analysis(cfg, root)
