from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd
from pyproj import Transformer

from config import CONFIG
from scripts.common.io_utils import load_json, project_root_from, resolve_path, runtime_cfg_for_comparison, save_csv, save_json

DESTINATION_GROUP_MAP = {
    "cbd_bus": "CBD-bound",
    "cbd_mrt": "CBD-bound",
    "airport_bus": "Airport-bound",
    "airport_mrt": "Airport-bound",
}

KEY_STATIONS = [
    "HarbourFront",
    "Keppel",
    "Cantonment",
    "Prince Edward Road",
    "Marina Bay",
    "Bayfront",
    "Raffles Place",
    "City Hall",
    "Shenton Way",
    "Changi Airport",
]

SVY21_TO_WGS84 = Transformer.from_crs("EPSG:3414", "EPSG:4326", always_xy=True)


def _looks_like_lonlat(x: float, y: float) -> bool:
    return -180.0 <= x <= 180.0 and -90.0 <= y <= 90.0


def _transform_geometry_to_lonlat(geom: Dict[str, Any]) -> Dict[str, Any]:
    gtype = geom.get("type")
    coords = geom.get("coordinates", [])

    def tx_pair(pair):
        x, y = float(pair[0]), float(pair[1])
        if _looks_like_lonlat(x, y):
            return [x, y]
        lon, lat = SVY21_TO_WGS84.transform(x, y)
        return [float(lon), float(lat)]

    if gtype == "Polygon":
        new_coords = [[[tx_pair(pt) for pt in ring] for ring in coords]] if coords and coords and isinstance(coords[0][0][0], (int,float)) else [[tx_pair(pt) for pt in ring] for ring in coords]
        # normalize accidental extra nesting
        if len(new_coords)==1 and len(coords)>0 and isinstance(coords[0][0][0], (int,float)):
            new_coords=new_coords[0]
        return {"type": "Polygon", "coordinates": new_coords}
    if gtype == "MultiPolygon":
        return {"type": "MultiPolygon", "coordinates": [[[tx_pair(pt) for pt in ring] for ring in poly] for poly in coords]}
    return geom


def _clean_saving(v: Any) -> float:
    try:
        x = float(v)
    except Exception:
        return 0.0
    if abs(x) < 1e-9:
        return 0.0
    if x < 0:
        return 0.0
    return x


def _clean_name(name: Any) -> str:
    if name is None:
        return ""
    return str(name).replace("_", " ").strip()


def _feature_bounds(geom: Dict[str, Any]) -> Tuple[float, float, float, float]:
    xs: List[float] = []
    ys: List[float] = []
    gtype = geom.get("type")
    coords = geom.get("coordinates", [])
    if gtype == "Polygon":
        polys = [coords]
    elif gtype == "MultiPolygon":
        polys = coords
    else:
        polys = []
    for poly in polys:
        for ring in poly:
            for x, y in ring:
                xs.append(float(x))
                ys.append(float(y))
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


def _pad_bbox(bounds: Tuple[float, float, float, float], frac: float = 0.06) -> Dict[str, float]:
    xmin, ymin, xmax, ymax = bounds
    dx = max(xmax - xmin, 1e-6)
    dy = max(ymax - ymin, 1e-6)
    return {
        "minLon": xmin - dx * frac,
        "maxLon": xmax + dx * frac,
        "minLat": ymin - dy * frac,
        "maxLat": ymax + dy * frac,
    }


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_nodes_lookup(project_root: Path, cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    nodes_path = resolve_path(project_root, cfg["paths"]["model"]["scenario"]["pre_ring"]["nodes_json"])
    payload = load_json(nodes_path)
    return {row["node_id"]: row for row in payload["nodes"]}


def _load_centroid_lookup(project_root: Path, cfg: Dict[str, Any]) -> Dict[Tuple[int, int], Dict[str, Any]]:
    centroids_path = resolve_path(project_root, cfg["paths"]["raw"]["spatial"]["centroids_geojson"])
    gj = load_json(centroids_path)
    out: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for feat in gj["features"]:
        p = feat["properties"]
        out[(int(p["row_index"]), int(p["col_index"]))] = {
            "origin_id": p["grid_id"],
            "row_index": int(p["row_index"]),
            "col_index": int(p["col_index"]),
            "lon": float(p["lon"]),
            "lat": float(p["lat"]),
            "x_svy": float(p["x_svy"]),
            "y_svy": float(p["y_svy"]),
        }
    return out


def _load_grid_features(project_root: Path, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    grids_path = resolve_path(project_root, cfg["paths"]["raw"]["spatial"]["clipped_grids_geojson"])
    gj = load_json(grids_path)
    feats = []
    for feat in gj["features"]:
        new_feat = dict(feat)
        new_feat["geometry"] = _transform_geometry_to_lonlat(feat["geometry"])
        feats.append(new_feat)
    return feats


def _load_comparison_df(project_root: Path, cfg: Dict[str, Any]) -> pd.DataFrame:
    comp_path = resolve_path(project_root, cfg["paths"]["analysis"]["comparison"]["od_shortest_paths_json"])
    payload = load_json(comp_path)
    df = pd.DataFrame(payload["records"])
    df["saving_min"] = (-pd.to_numeric(df["delta_time_min"], errors="coerce")).fillna(0.0).clip(lower=0.0)
    df["group_major"] = df["sink_set"].map(DESTINATION_GROUP_MAP)
    return df[df["group_major"].notna()].copy()


def _terminal_lookup(project_root: Path, cfg: Dict[str, Any], node_lookup: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    path = resolve_path(project_root, cfg["paths"]["model"]["scenario"]["pre_ring"]["terminal_sets_json"])
    payload = load_json(path)
    lookup: Dict[str, Dict[str, Any]] = {}
    for group_raw, rows in payload.get("detail", {}).items():
        if group_raw == "source_centroids" or group_raw not in DESTINATION_GROUP_MAP:
            continue
        for row in rows:
            node_id = row["node_id"]
            node = node_lookup.get(node_id, {})
            label = _clean_name(row.get("name") or row.get("station_name") or row.get("physical_station_name") or node.get("name") or node_id)
            lookup[node_id] = {
                "destination_id": node_id,
                "group_raw": group_raw,
                "group_major": DESTINATION_GROUP_MAP[group_raw],
                "group_label": group_raw.replace("_", " ").title(),
                "label": label,
                "lon": node.get("lon"),
                "lat": node.get("lat"),
            }
    return lookup


def _build_context(project_root: Path, cfg: Dict[str, Any], node_lookup: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    station_points = load_json(resolve_path(project_root, cfg["paths"]["raw"]["mrt"]["station_points_geojson"]))
    point_by_name: Dict[str, Dict[str, Any]] = {}
    point_by_code: Dict[str, Dict[str, Any]] = {}
    for feat in station_points["features"]:
        p = feat["properties"]
        lon, lat = feat["geometry"]["coordinates"]
        row = {
            "name": _clean_name(p.get("station_name")),
            "code": _clean_name(p.get("primary_code") or p.get("station_code")),
            "lon": float(lon),
            "lat": float(lat),
            "is_new": False,
        }
        if row["name"]:
            point_by_name[row["name"]] = row
        if row["code"]:
            point_by_code[row["code"]] = row

    new_stations_gj = load_json(resolve_path(project_root, cfg["paths"]["raw"]["scenario"]["cc_ring"]["new_mrt_stations_geojson"]))
    for feat in new_stations_gj["features"]:
        p = feat["properties"]
        row = {
            "name": _clean_name(p.get("name")),
            "code": _clean_name(p.get("code")),
            "lon": float(p["lon"]),
            "lat": float(p["lat"]),
            "is_new": True,
        }
        if row["name"]:
            point_by_name[row["name"]] = row
        if row["code"]:
            point_by_code[row["code"]] = row

    topology = load_json(resolve_path(project_root, cfg["paths"]["raw"]["mrt"]["route_topology_json"]))
    segments: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()
    for route in topology.values():
        stops = route.get("stops_matrix", [])
        for a, b in zip(stops[:-1], stops[1:]):
            code_a, code_b = _clean_name(a[1]), _clean_name(b[1])
            name_a, name_b = _clean_name(a[2]), _clean_name(b[2])
            pa = point_by_code.get(code_a) or point_by_name.get(name_a)
            pb = point_by_code.get(code_b) or point_by_name.get(name_b)
            if not pa or not pb:
                continue
            key = tuple(sorted((code_a or name_a, code_b or name_b)))
            if key in seen:
                continue
            seen.add(key)
            segments.append({
                "from": code_a or name_a,
                "to": code_b or name_b,
                "coords": [[pa["lon"], pa["lat"]], [pb["lon"], pb["lat"]]],
                "is_new": False,
            })

    ring_links = load_json(resolve_path(project_root, cfg["paths"]["raw"]["scenario"]["cc_ring"]["cc_ring_links_json"]))
    for row in ring_links:
        a, b = row["from_node"], row["to_node"]
        pa = point_by_code.get(a)
        pb = point_by_code.get(b)
        if not pa or not pb:
            continue
        key = tuple(sorted((a, b)))
        if key in seen:
            continue
        seen.add(key)
        segments.append({"from": a, "to": b, "coords": [[pa["lon"], pa["lat"]], [pb["lon"], pb["lat"]]], "is_new": True})

    mrt_stations = sorted(point_by_name.values(), key=lambda x: x["name"])
    key_stations: List[Dict[str, Any]] = []
    for name in KEY_STATIONS:
        if name == "Changi Airport":
            row = point_by_name.get(name)
        else:
            row = point_by_name.get(name)
        if row:
            key_stations.append({"name": name, "lon": row["lon"], "lat": row["lat"], "is_new": row["is_new"]})
        else:
            # fallback from graph nodes if needed
            matches = [n for n in node_lookup.values() if _clean_name(n.get("name")) == name and n.get("lon") is not None and n.get("lat") is not None]
            if matches:
                n = matches[0]
                key_stations.append({"name": name, "lon": float(n["lon"]), "lat": float(n["lat"]), "is_new": False})

    return {
        "mrt_segments": segments,
        "mrt_stations": mrt_stations,
        "key_stations": key_stations,
    }


def build_origin_impact_payload(cfg: Dict[str, Any], project_root: Path) -> Dict[str, str]:
    node_lookup = _load_nodes_lookup(project_root, cfg)
    centroid_lookup = _load_centroid_lookup(project_root, cfg)
    grid_features = _load_grid_features(project_root, cfg)
    df = _load_comparison_df(project_root, cfg)
    dest_lookup = _terminal_lookup(project_root, cfg, node_lookup)
    context = _build_context(project_root, cfg, node_lookup)

    origin_rows: List[Dict[str, Any]] = []
    bounds_list: List[Tuple[float, float, float, float]] = []
    for feat in grid_features:
        p = feat["properties"]
        key = (int(p["row_index"]), int(p["col_index"]))
        meta = centroid_lookup.get(key)
        if not meta:
            continue
        sub = df[df["source_id"] == meta["origin_id"]]
        cbd = sub[sub["group_major"] == "CBD-bound"]
        airport = sub[sub["group_major"] == "Airport-bound"]
        row = {
            **meta,
            "overall_mean_saving_min": round(float(sub["saving_min"].mean()) if len(sub) else 0.0, 3),
            "overall_median_saving_min": round(float(sub["saving_min"].median()) if len(sub) else 0.0, 3),
            "overall_share_improved": round(float((sub["saving_min"] > 0).mean()) if len(sub) else 0.0, 6),
            "cbd_mean_saving_min": round(float(cbd["saving_min"].mean()) if len(cbd) else 0.0, 3),
            "cbd_median_saving_min": round(float(cbd["saving_min"].median()) if len(cbd) else 0.0, 3),
            "cbd_share_improved": round(float((cbd["saving_min"] > 0).mean()) if len(cbd) else 0.0, 6),
            "airport_mean_saving_min": round(float(airport["saving_min"].mean()) if len(airport) else 0.0, 3),
            "airport_median_saving_min": round(float(airport["saving_min"].median()) if len(airport) else 0.0, 3),
            "airport_share_improved": round(float((airport["saving_min"] > 0).mean()) if len(airport) else 0.0, 6),
            "geometry": feat["geometry"],
        }
        origin_rows.append(row)
        bounds_list.append(_feature_bounds(feat["geometry"]))

    origin_rows = sorted(origin_rows, key=lambda r: (r["col_index"], r["row_index"]))
    origin_order = [r["origin_id"] for r in origin_rows]

    destination_rows: List[Dict[str, Any]] = []
    destination_csv_rows: List[Dict[str, Any]] = []
    layers: Dict[str, Dict[str, Any]] = {}
    for dest_id, meta in sorted(dest_lookup.items(), key=lambda kv: (kv[1]["group_major"], kv[1]["label"])):
        sub = df[df["sink_id"] == dest_id].copy()
        values_by_origin = {row["source_id"]: round(float(row["saving_min"]), 3) for _, row in sub.iterrows()}
        layers[f"dest::{dest_id}"] = {
            "destination_id": dest_id,
            "values": [values_by_origin.get(origin_id, 0.0) for origin_id in origin_order],
        }
        vals = sub["saving_min"] if len(sub) else pd.Series(dtype=float)
        destination_rows.append(meta)
        destination_csv_rows.append({
            "destination_id": dest_id,
            "destination_label": meta["label"],
            "group_raw": meta["group_raw"],
            "group_major": meta["group_major"],
            "mean_saving_min": round(float(vals.mean()) if len(vals) else 0.0, 3),
            "median_saving_min": round(float(vals.median()) if len(vals) else 0.0, 3),
            "share_improved": round(float((vals > 0).mean()) if len(vals) else 0.0, 6),
            "n_origins": int(len(vals)),
            "lon": meta["lon"],
            "lat": meta["lat"],
        })

    od_long_rows: List[Dict[str, Any]] = []
    od_records: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        dest_meta = dest_lookup.get(row["sink_id"], {
            "label": row["sink_id"],
            "group_raw": row["sink_set"],
            "group_major": row["group_major"],
            "group_label": str(row["sink_set"]).replace("_", " ").title(),
            "lon": None,
            "lat": None,
        })
        out = {
            "origin_id": row["source_id"],
            "destination_id": row["sink_id"],
            "destination_label": dest_meta["label"],
            "destination_group_raw": dest_meta["group_raw"],
            "destination_group_major": dest_meta["group_major"],
            "destination_group_label": dest_meta["group_label"],
            "pre_time_min": round(float(row["pre_time_min"]), 3) if pd.notna(row["pre_time_min"]) else None,
            "post_time_min": round(float(row["post_time_min"]), 3) if pd.notna(row["post_time_min"]) else None,
            "saving_min": round(float(row["saving_min"]), 3),
            "change_type": row["change_type"],
        }
        od_long_rows.append(out)
        od_records.append({
            **out,
            "group_major": dest_meta["group_major"],
            "group_label": dest_meta["group_label"],
        })

    # bboxes
    if bounds_list:
        xmin = min(b[0] for b in bounds_list)
        ymin = min(b[1] for b in bounds_list)
        xmax = max(b[2] for b in bounds_list)
        ymax = max(b[3] for b in bounds_list)
    else:
        xmin = ymin = xmax = ymax = 0.0
    # include local context and CBD terminals in main bbox
    for row in destination_rows:
        if row["group_major"] == "CBD-bound" and row["lon"] is not None and row["lat"] is not None:
            xmin = min(xmin, float(row["lon"]))
            xmax = max(xmax, float(row["lon"]))
            ymin = min(ymin, float(row["lat"]))
            ymax = max(ymax, float(row["lat"]))
    for row in context["key_stations"]:
        if row["name"] != "Changi Airport":
            xmin = min(xmin, float(row["lon"]))
            xmax = max(xmax, float(row["lon"]))
            ymin = min(ymin, float(row["lat"]))
            ymax = max(ymax, float(row["lat"]))
    main_bbox = _pad_bbox((xmin, ymin, xmax, ymax), 0.08)

    airport_pts = [(float(r["lon"]), float(r["lat"])) for r in destination_rows if r["group_major"] == "Airport-bound" and r["lon"] is not None and r["lat"] is not None]
    if airport_pts:
        axmin = min(x for x, _ in airport_pts)
        axmax = max(x for x, _ in airport_pts)
        aymin = min(y for _, y in airport_pts)
        aymax = max(y for _, y in airport_pts)
        airport_bbox = _pad_bbox((axmin, aymin, axmax, aymax), 0.12)
    else:
        airport_bbox = {"minLon": 0.0, "maxLon": 1.0, "minLat": 0.0, "maxLat": 1.0}

    payload = {
        "meta": {
            "n_origins": len(origin_rows),
            "n_destinations": len(destination_rows),
            "n_od_pairs": len(od_records),
            "main_bbox": main_bbox,
            "airport_bbox": airport_bbox,
        },
        "origins": origin_rows,
        "destinations": destination_rows,
        "layers": layers,
        "od_records": od_records,
        "context": context,
    }

    origin_csv_path = resolve_path(project_root, cfg["paths"]["analysis"]["origin_impact"]["origin_csv"])
    destination_csv_path = resolve_path(project_root, cfg["paths"]["analysis"]["origin_impact"]["destination_csv"])
    od_long_csv_path = resolve_path(project_root, cfg["paths"]["analysis"]["origin_impact"]["od_long_csv"])
    payload_json_path = resolve_path(project_root, cfg["paths"]["analysis"]["origin_impact"]["payload_json"])

    save_csv(origin_csv_path, [{k: v for k, v in row.items() if k != "geometry"} for row in origin_rows])
    save_csv(destination_csv_path, destination_csv_rows)
    save_csv(od_long_csv_path, od_long_rows)
    save_json(payload_json_path, payload)

    return {
        "origin_csv": str(origin_csv_path.relative_to(project_root)),
        "destination_csv": str(destination_csv_path.relative_to(project_root)),
        "od_long_csv": str(od_long_csv_path.relative_to(project_root)),
        "payload_json": str(payload_json_path.relative_to(project_root)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build origin-side impact payload files")
    parser.add_argument("--project-root", type=Path, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg = runtime_cfg_for_comparison(CONFIG, ["pre_ring", "post_ring"])
    root = project_root_from(cfg, args.project_root)
    print(json.dumps(build_origin_impact_payload(cfg, root), ensure_ascii=False, indent=2))
