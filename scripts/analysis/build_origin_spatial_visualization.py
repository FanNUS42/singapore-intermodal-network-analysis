from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import PatchCollection
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Polygon as MplPolygon
from shapely.geometry import shape

from config import CONFIG
from scripts.analysis.build_origin_impact_dashboard import build_origin_impact_dashboard
from scripts.common.io_utils import load_json, project_root_from, resolve_path, runtime_cfg_for_comparison

COLOR_TITLE = "#243141"
COLOR_BODY = "#44505E"
COLOR_DIVIDER = "#C9D3DC"
COLOR_PANEL_BG = "#F8FAFC"
COLOR_EXISTING_LINK = "#D6DEE6"
COLOR_NEW_LINK = "#5D8B73"
COLOR_KEY_STATION = "#385A4A"
HEATMAP_CMAP = LinearSegmentedColormap.from_list("origin_saving", ["#F2F5F7", "#DCE8F1", "#B9D1E3", "#7DA6C7", "#4B789E", "#244B74"])
LABEL_OFFSETS = {
    "HarbourFront": (-18, -10),
    "Keppel": (-10, -14),
    "Cantonment": (-2, -14),
    "Prince Edward Road": (8, -12),
    "Marina Bay": (8, -8),
    "Bayfront": (8, 10),
    "Raffles Place": (8, 8),
    "City Hall": (8, -10),
    "Shenton Way": (8, 10),
}


def _iter_polygon_rings(geometry_dict: Dict[str, Any]) -> List[List[Tuple[float, float]]]:
    geom = shape(geometry_dict)
    rings: List[List[Tuple[float, float]]] = []
    if geom.geom_type == "Polygon":
        rings.append([(float(x), float(y)) for x, y in geom.exterior.coords])
    elif geom.geom_type == "MultiPolygon":
        for poly in geom.geoms:
            rings.append([(float(x), float(y)) for x, y in poly.exterior.coords])
    return rings


def _draw_main_context(ax: plt.Axes, payload: Dict[str, Any]) -> None:
    bbox = payload["meta"]["main_bbox"]
    xmin, xmax = bbox["minLon"], bbox["maxLon"]
    ymin, ymax = bbox["minLat"], bbox["maxLat"]
    ax.set_facecolor(COLOR_PANEL_BG)
    for seg in payload["context"]["mrt_segments"]:
        (x1, y1), (x2, y2) = seg["coords"]
        if ((x1 < xmin and x2 < xmin) or (x1 > xmax and x2 > xmax) or (y1 < ymin and y2 < ymin) or (y1 > ymax and y2 > ymax)):
            continue
        ax.plot([x1, x2], [y1, y2], color=COLOR_NEW_LINK if seg["is_new"] else COLOR_EXISTING_LINK, linewidth=1.5 if seg["is_new"] else 0.75, zorder=1, solid_capstyle="round")
    stations = [s for s in payload["context"]["mrt_stations"] if xmin <= s["lon"] <= xmax and ymin <= s["lat"] <= ymax]
    if stations:
        ax.scatter([s["lon"] for s in stations], [s["lat"] for s in stations], s=[16 if s["is_new"] else 7 for s in stations], c=[COLOR_NEW_LINK if s["is_new"] else "#B8C4CF" for s in stations], zorder=2, linewidths=0)
    key_stations = [s for s in payload["context"]["key_stations"] if s["name"] != "Changi Airport" and xmin <= s["lon"] <= xmax and ymin <= s["lat"] <= ymax]
    if key_stations:
        ax.scatter([s["lon"] for s in key_stations], [s["lat"] for s in key_stations], s=12, c=COLOR_KEY_STATION, zorder=3)
        for row in key_stations:
            dx, dy = LABEL_OFFSETS.get(row["name"], (6, 6))
            ax.annotate(row["name"], xy=(row["lon"], row["lat"]), xytext=(dx, dy), textcoords="offset points", fontsize=7.3, color=COLOR_TITLE, zorder=4)
    for spine in ax.spines.values():
        spine.set_color(COLOR_DIVIDER)
        spine.set_linewidth(0.8)
    ax.set_xticks([])
    ax.set_yticks([])


def _draw_airport_inset(ax: plt.Axes, payload: Dict[str, Any]) -> None:
    airport_rows = [row for row in payload["destinations"] if row["group_major"] == "Airport-bound" and row["lon"] is not None and row["lat"] is not None]
    if not airport_rows:
        return
    bbox = payload["meta"]["airport_bbox"]
    ax.set_facecolor("#FCFDFE")
    ax.set_xlim(bbox["minLon"], bbox["maxLon"])
    ax.set_ylim(bbox["minLat"], bbox["maxLat"])
    ax.scatter([r["lon"] for r in airport_rows], [r["lat"] for r in airport_rows], s=24, facecolors="#ffffff", edgecolors=COLOR_KEY_STATION, linewidths=0.8, zorder=2)
    airport_mrt = [r for r in airport_rows if r["group_raw"] == "airport_mrt"]
    if airport_mrt:
        ax.scatter([r["lon"] for r in airport_mrt], [r["lat"] for r in airport_mrt], s=48, c="#CF9245", edgecolors=COLOR_KEY_STATION, linewidths=0.9, zorder=3)
    ax.text(0.04, 0.96, "Airport terminals", transform=ax.transAxes, ha="left", va="top", fontsize=6.8, color=COLOR_TITLE, fontweight="bold")
    ax.text(0.04, 0.06, "Detached inset\nnot to scale", transform=ax.transAxes, ha="left", va="bottom", fontsize=6.0, color=COLOR_BODY)
    for spine in ax.spines.values():
        spine.set_color(COLOR_DIVIDER)
        spine.set_linewidth(0.75)
    ax.set_xticks([])
    ax.set_yticks([])


def _origin_bounds(origin_rows: List[Dict[str, Any]]) -> Tuple[float, float, float, float]:
    xs: List[float] = []
    ys: List[float] = []
    for row in origin_rows:
        geom = shape(row["geometry"])
        minx, miny, maxx, maxy = geom.bounds
        xs.extend([float(minx), float(maxx)])
        ys.extend([float(miny), float(maxy)])
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    xpad = max((xmax - xmin) * 0.035, 1e-6)
    ypad = max((ymax - ymin) * 0.045, 1e-6)
    return xmin - xpad, xmax + xpad, ymin - ypad, ymax + ypad


def create_origin_spatial_saving_heatmap(payload: Dict[str, Any], output_path: Path) -> None:
    origin_rows = payload["origins"]
    xmin, xmax, ymin, ymax = _origin_bounds(origin_rows)
    panel_fields = [
        ("overall_mean_saving_min", "(a) Overall"),
        ("cbd_mean_saving_min", "(b) CBD-bound"),
        ("airport_mean_saving_min", "(c) Airport-bound"),
    ]
    vmax = max(max(float(row[field]) for row in origin_rows) for field, _ in panel_fields)
    vmax = max(vmax, 0.5)
    norm = Normalize(vmin=0.0, vmax=vmax)

    fig, axes = plt.subplots(1, 3, figsize=(12.6, 3.55), dpi=220, facecolor="white")
    mapper = plt.cm.ScalarMappable(norm=norm, cmap=HEATMAP_CMAP)

    for ax, (field, title) in zip(axes, panel_fields):
        patches = []
        colors = []
        for row in origin_rows:
            for ring in _iter_polygon_rings(row["geometry"]):
                patches.append(MplPolygon(ring, closed=True))
                colors.append(float(row[field]))
        pc = PatchCollection(patches, cmap=HEATMAP_CMAP, norm=norm, linewidth=0.30, edgecolor="#FFFFFF", zorder=1)
        pc.set_array(np.array(colors))
        ax.add_collection(pc)
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.set_aspect("equal", adjustable="box")
        ax.set_facecolor("white")
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_title(title, fontsize=10.5, fontweight="semibold", color=COLOR_TITLE, pad=6)
        values = pd.Series([float(row[field]) for row in origin_rows])

    cax = fig.add_axes([0.34, 0.09, 0.32, 0.06])
    cbar = fig.colorbar(mapper, cax=cax, orientation="horizontal")
    cbar.outline.set_color(COLOR_DIVIDER)
    cbar.outline.set_linewidth(0.7)
    cbar.ax.tick_params(labelsize=8.2, colors=COLOR_BODY)
    cbar.set_label("Mean origin-level travel-time saving (min)", fontsize=8.7, color=COLOR_BODY)

    fig.subplots_adjust(left=0.025, right=0.985, top=0.84, bottom=0.20, wspace=0.02)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, facecolor="white", bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)


def build_origin_spatial_visualization(cfg: Dict[str, Any], project_root: Path) -> Dict[str, str]:
    payload_path = resolve_path(project_root, cfg["paths"]["analysis"]["origin_impact"]["payload_json"])
    payload = load_json(payload_path)
    heatmap_path = resolve_path(project_root, cfg["paths"]["analysis"]["visualization"]["origin_heatmap_png"])
    create_origin_spatial_saving_heatmap(payload, heatmap_path)
    html_out = build_origin_impact_dashboard(cfg, project_root)
    return {
        "origin_heatmap_png": str(heatmap_path.relative_to(project_root)),
        **html_out,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build origin-side visualization outputs")
    parser.add_argument("--project-root", type=Path, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg = runtime_cfg_for_comparison(CONFIG, ["pre_ring", "post_ring"])
    root = project_root_from(cfg, args.project_root)
    print(json.dumps(build_origin_spatial_visualization(cfg, root), ensure_ascii=False, indent=2))
