from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List

from config import CONFIG
from scripts.common.io_utils import (
    load_json,
    project_root_from,
    resolve_path,
    runtime_cfg_for_comparison,
    save_csv,
    save_json,
)


def _record_index(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(row["station_id"]): row for row in payload.get("records", []) if row.get("station_id")}


def _rank_map(rows: List[Dict[str, Any]], key: str, reverse: bool = True) -> Dict[str, int]:
    ordered = sorted(rows, key=lambda r: (float(r.get(key, 0.0)), str(r.get("station_id"))), reverse=reverse)
    return {str(row["station_id"]): idx for idx, row in enumerate(ordered, start=1)}


def compare_mrt_station_centrality(cfg: Dict[str, Any], project_root: Path) -> Dict[str, Any]:
    runtime = cfg.get("_runtime", {})
    scenario_names = runtime.get("comparison_scenarios") or ["pre_ring", "post_ring"]
    if len(scenario_names) != 2:
        raise ValueError("compare_mrt_station_centrality expects exactly two scenarios")
    pre_name, post_name = scenario_names

    scenario_paths = cfg["paths"]["analysis"]["scenario"]
    pre_path = resolve_path(project_root, scenario_paths[pre_name]["mrt_station_centrality_json"])
    post_path = resolve_path(project_root, scenario_paths[post_name]["mrt_station_centrality_json"])
    out_csv_path = resolve_path(project_root, cfg["paths"]["analysis"]["comparison"]["mrt_station_centrality_csv"])
    out_json_path = resolve_path(project_root, cfg["paths"]["analysis"]["comparison"]["mrt_station_centrality_json"])

    pre_payload = load_json(pre_path)
    post_payload = load_json(post_path)
    pre_index = _record_index(pre_payload)
    post_index = _record_index(post_payload)
    all_station_ids = sorted(set(pre_index) | set(post_index))

    rows: List[Dict[str, Any]] = []
    for station_id in all_station_ids:
        pre = pre_index.get(station_id)
        post = post_index.get(station_id)
        row_base = post or pre or {}
        bet_pre = pre.get("betweenness") if pre else None
        bet_post = post.get("betweenness") if post else None
        clo_pre = pre.get("closeness") if pre else None
        clo_post = post.get("closeness") if post else None
        rows.append(
            {
                "station_id": station_id,
                "station_name": row_base.get("station_name"),
                "is_new_in_post": bool((pre is None) and (post is not None)),
                "is_removed_in_post": bool((pre is not None) and (post is None)),
                "is_interchange": row_base.get("is_interchange"),
                "station_codes": "|".join(row_base.get("station_codes", [])),
                "line_names": "|".join(row_base.get("line_names", [])),
                "lat": row_base.get("lat"),
                "lon": row_base.get("lon"),
                "betweenness_pre": bet_pre,
                "betweenness_post": bet_post,
                "betweenness_delta": round(float(bet_post) - float(bet_pre), 8) if bet_pre is not None and bet_post is not None else None,
                "closeness_pre": clo_pre,
                "closeness_post": clo_post,
                "closeness_delta": round(float(clo_post) - float(clo_pre), 8) if clo_pre is not None and clo_post is not None else None,
                "out_degree_pre": pre.get("out_degree") if pre else None,
                "out_degree_post": post.get("out_degree") if post else None,
                "in_degree_pre": pre.get("in_degree") if pre else None,
                "in_degree_post": post.get("in_degree") if post else None,
            }
        )

    bet_delta_rank = _rank_map([r for r in rows if r.get("betweenness_delta") is not None], "betweenness_delta", reverse=True)
    clo_delta_rank = _rank_map([r for r in rows if r.get("closeness_delta") is not None], "closeness_delta", reverse=True)
    for row in rows:
        sid = str(row["station_id"])
        row["betweenness_delta_rank_desc"] = bet_delta_rank.get(sid)
        row["closeness_delta_rank_desc"] = clo_delta_rank.get(sid)

    rows.sort(key=lambda r: (r["is_new_in_post"], float(r.get("betweenness_delta") or -999), float(r.get("closeness_delta") or -999), str(r["station_id"])), reverse=True)
    save_csv(out_csv_path, rows)

    payload = {
        "meta": {
            "comparison": [pre_name, post_name],
            "input_files": {
                pre_name: str(pre_path.relative_to(project_root)),
                post_name: str(post_path.relative_to(project_root)),
            },
            "output_csv": str(out_csv_path.relative_to(project_root)),
            "record_count": len(rows),
        },
        "top_betweenness_increase": sorted([r for r in rows if r.get("betweenness_delta") is not None], key=lambda r: float(r["betweenness_delta"]), reverse=True)[:20],
        "top_closeness_increase": sorted([r for r in rows if r.get("closeness_delta") is not None], key=lambda r: float(r["closeness_delta"]), reverse=True)[:20],
        "records": rows,
    }
    save_json(out_json_path, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare MRT physical-station centrality results between two scenarios")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--pre", type=str, default="pre_ring")
    parser.add_argument("--post", type=str, default="post_ring")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg = runtime_cfg_for_comparison(CONFIG, [args.pre, args.post])
    root = project_root_from(cfg, args.project_root)
    compare_mrt_station_centrality(cfg, root)
