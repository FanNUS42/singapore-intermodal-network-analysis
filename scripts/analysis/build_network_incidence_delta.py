from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from config import CONFIG
from scripts.analysis.path_analysis_utils import (
    extract_line_hits,
    extract_segment_hits,
    extract_station_hits,
    load_links_lookup,
    load_nodes_lookup,
    materialize_incidence_rows,
    top_counter_deltas,
    update_incidence_counter,
)
from scripts.common.io_utils import load_json, project_root_from, resolve_path, runtime_cfg_for_comparison, save_csv, save_json



def _update_meta_store(meta_store: Dict[str, Dict[str, Any]], hits: Dict[str, Dict[str, Any]]) -> None:
    for key, value in hits.items():
        if key not in meta_store:
            meta_store[key] = value



def build_network_incidence_delta(cfg: Dict[str, Any], project_root: Path) -> Dict[str, Any]:
    runtime = cfg.get("_runtime", {})
    scenario_names = runtime.get("comparison_scenarios") or ["pre_ring", "post_ring"]
    if len(scenario_names) != 2:
        raise ValueError("build_network_incidence_delta expects exactly two scenarios")
    pre_name, post_name = scenario_names

    compare_path = resolve_path(project_root, cfg["paths"]["analysis"]["comparison"]["od_shortest_paths_json"])
    pre_nodes_path = resolve_path(project_root, cfg["paths"]["model"]["scenario"][pre_name]["nodes_json"])
    pre_links_path = resolve_path(project_root, cfg["paths"]["model"]["scenario"][pre_name]["links_json"])
    post_nodes_path = resolve_path(project_root, cfg["paths"]["model"]["scenario"][post_name]["nodes_json"])
    post_links_path = resolve_path(project_root, cfg["paths"]["model"]["scenario"][post_name]["links_json"])
    out_cfg = cfg["paths"]["analysis"]["comparison"]["network_incidence"]
    station_csv_path = resolve_path(project_root, out_cfg["station_csv"])
    line_csv_path = resolve_path(project_root, out_cfg["line_csv"])
    segment_csv_path = resolve_path(project_root, out_cfg["segment_csv"])
    summary_json_path = resolve_path(project_root, out_cfg["summary_json"])

    compare_payload = load_json(compare_path)
    pre_nodes = load_nodes_lookup(pre_nodes_path)
    pre_links = load_links_lookup(pre_links_path)
    post_nodes = load_nodes_lookup(post_nodes_path)
    post_links = load_links_lookup(post_links_path)

    counters = {
        "station": {
            "meta": {},
            "pre_all": Counter(),
            "post_all": Counter(),
            "pre_changed": Counter(),
            "post_changed": Counter(),
        },
        "line": {
            "meta": {},
            "pre_all": Counter(),
            "post_all": Counter(),
            "pre_changed": Counter(),
            "post_changed": Counter(),
        },
        "segment": {
            "meta": {},
            "pre_all": Counter(),
            "post_all": Counter(),
            "pre_changed": Counter(),
            "post_changed": Counter(),
        },
    }

    for record in compare_payload.get("records", []):
        pre_path_node_ids = list(record.get("pre_path_node_ids") or [])
        post_path_node_ids = list(record.get("post_path_node_ids") or [])
        pre_path_link_ids = list(record.get("pre_path_link_ids") or [])
        post_path_link_ids = list(record.get("post_path_link_ids") or [])
        path_changed = bool(record.get("path_changed"))

        pre_station_hits = extract_station_hits(pre_path_node_ids, pre_nodes)
        post_station_hits = extract_station_hits(post_path_node_ids, post_nodes)
        pre_line_hits = extract_line_hits(pre_path_link_ids, pre_links)
        post_line_hits = extract_line_hits(post_path_link_ids, post_links)
        pre_segment_hits = extract_segment_hits(pre_path_link_ids, pre_links)
        post_segment_hits = extract_segment_hits(post_path_link_ids, post_links)

        for family, pre_hits, post_hits in [
            ("station", pre_station_hits, post_station_hits),
            ("line", pre_line_hits, post_line_hits),
            ("segment", pre_segment_hits, post_segment_hits),
        ]:
            _update_meta_store(counters[family]["meta"], pre_hits)
            _update_meta_store(counters[family]["meta"], post_hits)
            update_incidence_counter(counters[family]["pre_all"], pre_hits)
            update_incidence_counter(counters[family]["post_all"], post_hits)
            if path_changed:
                update_incidence_counter(counters[family]["pre_changed"], pre_hits)
                update_incidence_counter(counters[family]["post_changed"], post_hits)

    station_rows = materialize_incidence_rows(
        counters["station"]["meta"],
        counters["station"]["pre_all"],
        counters["station"]["post_all"],
        counters["station"]["pre_changed"],
        counters["station"]["post_changed"],
    )
    line_rows = materialize_incidence_rows(
        counters["line"]["meta"],
        counters["line"]["pre_all"],
        counters["line"]["post_all"],
        counters["line"]["pre_changed"],
        counters["line"]["post_changed"],
    )
    segment_rows = materialize_incidence_rows(
        counters["segment"]["meta"],
        counters["segment"]["pre_all"],
        counters["segment"]["post_all"],
        counters["segment"]["pre_changed"],
        counters["segment"]["post_changed"],
    )

    save_csv(station_csv_path, station_rows)
    save_csv(line_csv_path, line_rows)
    save_csv(segment_csv_path, segment_rows)

    summary = {
        "comparison": [pre_name, post_name],
        "input_compare_file": str(compare_path.relative_to(project_root)),
        "station": {
            "row_count": len(station_rows),
            **top_counter_deltas(station_rows),
        },
        "line": {
            "row_count": len(line_rows),
            **top_counter_deltas(line_rows),
        },
        "segment": {
            "row_count": len(segment_rows),
            **top_counter_deltas(segment_rows),
        },
        "output_files": {
            "station_csv": str(station_csv_path.relative_to(project_root)),
            "line_csv": str(line_csv_path.relative_to(project_root)),
            "segment_csv": str(segment_csv_path.relative_to(project_root)),
        },
    }
    save_json(summary_json_path, summary)
    return summary



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build network element path-incidence delta tables for a scenario comparison")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--pre", type=str, default="pre_ring")
    parser.add_argument("--post", type=str, default="post_ring")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg = runtime_cfg_for_comparison(CONFIG, [args.pre, args.post])
    root = project_root_from(cfg, args.project_root)
    build_network_incidence_delta(cfg, root)
