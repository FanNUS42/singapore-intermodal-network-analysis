from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Patch
from matplotlib.ticker import FixedLocator, FuncFormatter

from config import CONFIG
from scripts.common.io_utils import (
    load_json,
    project_root_from,
    resolve_path,
    runtime_cfg_for_comparison,
    save_csv,
    save_json,
)

DESTINATION_GROUP_MAP = {
    "cbd_bus": "CBD-bound",
    "cbd_mrt": "CBD-bound",
    "airport_bus": "Airport-bound",
    "airport_mrt": "Airport-bound",
}

OD_SUMMARY_ROW_ORDER = [
    ("Coverage", None),
    ("OD pairs (N)", "n_total"),
    ("Improved OD pairs, n (%)", "improved_n_pct"),
    ("Unchanged OD pairs, n (%)", "unchanged_n_pct"),
    ("Magnitude of saving", None),
    ("Mean saving (min)", "saving_mean"),
    ("Median saving (min)", "saving_median"),
    ("90th percentile saving (min)", "saving_p90"),
    ("Maximum saving (min)", "saving_max"),
    ("Mean saving among improved OD pairs (min)", "saving_mean_improved_only"),
    ("Median saving among improved OD pairs (min)", "saving_median_improved_only"),
    ("90th percentile saving among improved OD pairs (min)", "saving_p90_improved_only"),
]

COLOR_TITLE = "#2F3845"
COLOR_SECONDARY = "#5E7286"
COLOR_PRIMARY = "#C9D8E6"
COLOR_PANEL_BG = "#E9EFF3"
COLOR_DIVIDER = "#B8C0C8"
COLOR_BODY = "#3E4650"

COLOR_BUS_MEAN = "#6E89A6"
COLOR_BUS_MEDIAN = "#AFC4D9"
COLOR_MRT_MEAN = "#4F5A69"
COLOR_MRT_MEDIAN = "#9CA8B6"


def _percent_fmt(y: float, _: float) -> str:
    return f"{y * 100:.0f}%"


def _clean_saving_series(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce").fillna(0.0).astype(float)
    s[np.isclose(s, 0.0, atol=1e-9)] = 0.0
    if (s < -1e-9).any():
        raise ValueError("Negative travel-time saving detected. Expected non-negative savings only.")
    return s


def _cdf_unique(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    vals = np.sort(values.astype(float))
    uniq, counts = np.unique(vals, return_counts=True)
    cum = np.cumsum(counts).astype(float) / float(len(vals))
    return uniq, cum


def _tick_step_for(limit: float) -> float:
    if limit <= 2:
        return 0.5
    if limit <= 5:
        return 1.0
    if limit <= 10:
        return 2.0
    return 4.0


def _ticks_within(limit: float, step: float) -> np.ndarray:
    if limit <= 0:
        return np.array([0.0])
    max_tick = np.floor(limit / step) * step
    ticks = np.arange(0.0, max_tick + 1e-9, step)
    if len(ticks) == 0 or not np.isclose(ticks[0], 0.0):
        ticks = np.insert(ticks, 0, 0.0)
    return ticks


def _improved_ticks() -> np.ndarray:
    return np.array([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])


def _terminal_type_from_sink_id_or_set(sink_id: str, sink_set: str) -> str:
    if isinstance(sink_set, str):
        if sink_set.endswith("_bus"):
            return "Bus"
        if sink_set.endswith("_mrt"):
            return "MRT"
    if isinstance(sink_id, str):
        if sink_id.startswith("BUSSTOP_"):
            return "Bus"
        if sink_id.startswith("MRTHUB::"):
            return "MRT"
    return ""


def _clean_terminal_name(name: str) -> str:
    if not isinstance(name, str):
        return ""
    text = name.strip().replace("_", " ")
    return text


def style_panel(ax: plt.Axes) -> None:
    ax.set_facecolor(COLOR_PANEL_BG)
    ax.spines["top"].set_visible(False)
    for side in ["left", "bottom", "right"]:
        ax.spines[side].set_color(COLOR_DIVIDER)
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(colors=COLOR_BODY, labelsize=8.5)
    ax.grid(True, axis="y", color=COLOR_DIVIDER, linewidth=0.8)
    ax.grid(False, axis="x")


def load_comparison_df(cfg: Dict[str, Any], project_root: Path) -> pd.DataFrame:
    comparison_path = resolve_path(project_root, cfg["paths"]["analysis"]["comparison"]["od_shortest_paths_json"])
    payload = load_json(comparison_path)
    df = pd.DataFrame(payload["records"])
    df["saving_min"] = -pd.to_numeric(df["delta_time_min"], errors="coerce")
    df["saving_min"] = _clean_saving_series(df["saving_min"])
    df["destination_group"] = df["sink_set"].map(DESTINATION_GROUP_MAP)
    return df[df["destination_group"].notna()].copy()


def ordered_od_groups(df: pd.DataFrame) -> List[tuple[str, pd.Series]]:
    return [
        ("Overall", _clean_saving_series(df["saving_min"])),
        ("CBD-bound", _clean_saving_series(df.loc[df["destination_group"] == "CBD-bound", "saving_min"])),
        ("Airport-bound", _clean_saving_series(df.loc[df["destination_group"] == "Airport-bound", "saving_min"])),
    ]


def apply_single_curve_dual_scale(
    ax: plt.Axes,
    series: pd.Series,
    title: str,
    x_upper: float,
    x_tick_step: float,
    x_label: str,
    left_population_label: str,
    right_population_label: str,
) -> plt.Axes:
    s = _clean_saving_series(series)
    values = s.to_numpy(dtype=float)
    improved_share = float((values > 0).mean())
    unchanged_share = 1.0 - improved_share

    x, y = _cdf_unique(values)
    ax.step(
        x,
        y,
        where="post",
        color=COLOR_TITLE,
        linewidth=1.9,
        solid_capstyle="butt",
        clip_on=True,
        zorder=3,
    )
    ax.set_xlim(0.0, x_upper)
    ax.set_ylim(unchanged_share, 1.0)
    ax.set_title(title, fontsize=10, fontweight="bold", color=COLOR_TITLE, pad=8)
    ax.set_xlabel(x_label, fontsize=8.7, color=COLOR_BODY)
    ax.set_ylabel("")
    ax.yaxis.set_major_formatter(FuncFormatter(_percent_fmt))
    ax.xaxis.set_major_locator(FixedLocator(_ticks_within(x_upper, x_tick_step)))
    style_panel(ax)

    ax.text(
        0.98,
        0.06,
        f"Improved: {improved_share * 100:.1f}%",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=8.0,
        color=COLOR_TITLE,
        bbox=dict(boxstyle="round,pad=0.22", facecolor=COLOR_PRIMARY, edgecolor=COLOR_DIVIDER, linewidth=0.6),
    )

    ax2 = ax.twinx()
    ax2.set_facecolor("none")
    ax2.spines["top"].set_visible(False)
    ax2.spines["left"].set_visible(False)
    ax2.spines["right"].set_color(COLOR_DIVIDER)
    ax2.spines["right"].set_linewidth(0.8)
    ax2.tick_params(colors=COLOR_BODY, labelsize=8.5)
    ax2.grid(False)
    ax2.set_ylabel("")
    ax2.set_ylim(ax.get_ylim())
    imp_ticks = _improved_ticks()
    if improved_share <= 0:
        positions = np.full_like(imp_ticks, unchanged_share)
    else:
        positions = unchanged_share + imp_ticks * improved_share
    ax2.yaxis.set_major_locator(FixedLocator(positions))
    ax2.set_yticklabels([f"{v * 100:.0f}%" for v in imp_ticks])

    ax.text(-0.12, 1.01, left_population_label, transform=ax.transAxes, ha="left", va="bottom", fontsize=0.01, color="white")
    ax2.text(1.08, 1.01, right_population_label, transform=ax.transAxes, ha="right", va="bottom", fontsize=0.01, color="white")
    return ax2


def create_od_travel_time_saving_cdf(df: pd.DataFrame, output_path: Path) -> None:
    groups = ordered_od_groups(df)
    x_uppers = [max(float(series.max()), 0.5) for _, series in groups]
    x_steps = [_tick_step_for(v) for v in x_uppers]
    width_ratios = [x_uppers[0], x_uppers[1], max(x_uppers[2] * 0.82, 1.6)]

    fig = plt.figure(figsize=(12.2, 4.8), dpi=220, facecolor="white")
    gs = GridSpec(1, 3, figure=fig, width_ratios=width_ratios)
    axes = [fig.add_subplot(gs[0, i]) for i in range(3)]

    titles = ["(a) Overall", "(b) CBD-bound", "(c) Airport-bound"]
    for ax, (_, series), title, xmax, step in zip(axes, groups, titles, x_uppers, x_steps):
        apply_single_curve_dual_scale(
            ax=ax,
            series=series,
            title=title,
            x_upper=xmax,
            x_tick_step=step,
            x_label="Travel-time saving (min)",
            left_population_label="all OD pairs",
            right_population_label="improved OD pairs",
        )

    fig.subplots_adjust(left=0.065, right=0.992, top=0.84, bottom=0.19, wspace=0.30)
    fig.text(0.065, 0.06, "Note: Left axis = share of all OD pairs; right axis = share of improved OD pairs.", ha="left", va="bottom", fontsize=8.2, color=COLOR_BODY)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, facecolor="white", bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)


def create_origin_aggregated_saving_cdf(df: pd.DataFrame, output_path: Path) -> None:
    agg = (
        df.groupby(["source_id", "destination_group"], as_index=False)["saving_min"]
        .mean()
        .rename(columns={"saving_min": "mean_saving_min"})
    )
    cbd = _clean_saving_series(agg.loc[agg["destination_group"] == "CBD-bound", "mean_saving_min"])
    airport = _clean_saving_series(agg.loc[agg["destination_group"] == "Airport-bound", "mean_saving_min"])

    fig, axes = plt.subplots(1, 2, figsize=(9.4, 4.15), dpi=220, facecolor="white")
    for ax, series, title in zip(axes, [cbd, airport], ["(a) CBD-bound", "(b) Airport-bound"]):
        xmax = max(float(series.max()), 0.5)
        apply_single_curve_dual_scale(
            ax=ax,
            series=series,
            title=title,
            x_upper=xmax,
            x_tick_step=1.0,
            x_label="Mean origin-level travel-time saving (min)",
            left_population_label="all origins",
            right_population_label="improved origins",
        )

    fig.subplots_adjust(left=0.08, right=0.992, top=0.84, bottom=0.18, wspace=0.30)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, facecolor="white", bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)


def load_destination_terminal_lookup(cfg: Dict[str, Any], project_root: Path) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}

    scenario = "pre_ring"
    terminal_sets_path = project_root / "model" / "scenario" / scenario / "terminal_sets.json"
    if terminal_sets_path.exists():
        payload = load_json(terminal_sets_path)
        detail = payload.get("detail", {})
        for key in ["cbd_bus", "cbd_mrt", "airport_bus", "airport_mrt"]:
            for item in detail.get(key, []):
                node_id = item.get("node_id")
                if not node_id:
                    continue
                station_type = _terminal_type_from_sink_id_or_set(node_id, key)
                station_name = item.get("name") or item.get("station_name") or item.get("physical_station_name") or ""
                lookup[node_id] = {
                    "station_name": _clean_terminal_name(str(station_name)),
                    "station_type": station_type,
                    "terminal_label": _clean_terminal_name(str(station_name)),
                }

    bus_base_path = project_root / "model" / "base" / "bus_base.json"
    if bus_base_path.exists():
        payload = load_json(bus_base_path)
        for item in payload.get("stop_hubs", []):
            stop_name = _clean_terminal_name(str(item.get("stop_name", "")))
            for node_id in [item.get("board_node_id"), item.get("alight_node_id")]:
                if not node_id:
                    continue
                lookup.setdefault(node_id, {
                    "station_name": stop_name,
                    "station_type": "Bus",
                    "terminal_label": stop_name,
                })

    mrt_base_path = project_root / "model" / "base" / "mrt_base.json"
    if mrt_base_path.exists():
        payload = load_json(mrt_base_path)
        for item in payload.get("station_hubs", []):
            node_id = item.get("hub_id")
            if not node_id:
                continue
            station_name = _clean_terminal_name(str(item.get("physical_station_name", "")))
            lookup.setdefault(node_id, {
                "station_name": station_name,
                "station_type": "MRT",
                "terminal_label": station_name,
            })

    return lookup


def build_destination_terminal_df(df: pd.DataFrame, terminal_lookup: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
    grouped = (
        df.groupby(["sink_id", "sink_set", "destination_group"], as_index=False)
        .agg(
            n_origins=("saving_min", "size"),
            improved_origins_n=("saving_min", lambda s: int((_clean_saving_series(pd.Series(s)) > 0).sum())),
            mean_saving_min=("saving_min", "mean"),
            median_saving_min=("saving_min", "median"),
            p90_saving_min=("saving_min", lambda s: float(np.percentile(_clean_saving_series(pd.Series(s)), 90))),
            max_saving_min=("saving_min", "max"),
        )
        .copy()
    )

    grouped["improved_origins_pct"] = grouped["improved_origins_n"] / grouped["n_origins"]
    grouped["station_type"] = grouped.apply(
        lambda row: terminal_lookup.get(row["sink_id"], {}).get("station_type")
        or _terminal_type_from_sink_id_or_set(str(row["sink_id"]), str(row["sink_set"])),
        axis=1,
    )
    grouped["station_name"] = grouped.apply(
        lambda row: terminal_lookup.get(row["sink_id"], {}).get("station_name") or str(row["sink_id"]),
        axis=1,
    )
    grouped["terminal_label"] = grouped["station_name"]

    sort_cols = ["destination_group", "mean_saving_min", "median_saving_min", "improved_origins_pct", "terminal_label"]
    grouped = grouped.sort_values(sort_cols, ascending=[True, False, False, False, True]).reset_index(drop=True)
    grouped["rank_within_group"] = grouped.groupby("destination_group").cumcount() + 1

    for col in ["mean_saving_min", "median_saving_min", "p90_saving_min", "max_saving_min"]:
        grouped[col] = grouped[col].round(3)

    return grouped


def _mode_metric_color(mode: str, metric: str) -> str:
    if mode == "MRT":
        return COLOR_MRT_MEAN if metric == "mean" else COLOR_MRT_MEDIAN
    return COLOR_BUS_MEAN if metric == "mean" else COLOR_BUS_MEDIAN


def create_destination_terminal_saving_bar(
    dest_df: pd.DataFrame,
    output_path: Path,
    cbd_top_n: int = 10,
) -> None:
    cbd = (
        dest_df.loc[dest_df["destination_group"] == "CBD-bound"]
        .sort_values(["mean_saving_min", "median_saving_min", "improved_origins_pct"], ascending=[False, False, False])
        .head(cbd_top_n)
        .iloc[::-1]
        .copy()
    )
    airport = (
        dest_df.loc[dest_df["destination_group"] == "Airport-bound"]
        .sort_values(["mean_saving_min", "median_saving_min", "improved_origins_pct"], ascending=[False, False, False])
        .iloc[::-1]
        .copy()
    )

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(12.8, 5.7),
        dpi=220,
        facecolor="white",
        gridspec_kw={"width_ratios": [1.45, 1.0]},
    )

    for ax, part, title in zip(
        axes,
        [cbd, airport],
        ["(a) CBD terminals", "(b) Airport terminals"],
    ):
        style_panel(ax)
        y = np.arange(len(part), dtype=float)
        h = 0.34
        mean_colors = [_mode_metric_color(mode, "mean") for mode in part["station_type"]]
        median_colors = [_mode_metric_color(mode, "median") for mode in part["station_type"]]

        ax.barh(y + h / 2, part["mean_saving_min"].astype(float), height=h, color=mean_colors, edgecolor="none", zorder=3)
        ax.barh(y - h / 2, part["median_saving_min"].astype(float), height=h, color=median_colors, edgecolor="none", zorder=3)

        ax.set_yticks(y)
        ax.set_yticklabels(part["terminal_label"].tolist(), fontsize=8.5, color=COLOR_BODY)
        ax.set_title(title, fontsize=10, fontweight="bold", color=COLOR_TITLE, pad=8)
        if title == "(b) Airport terminals":
            ax.text(
                0.98,
                0.03,
                "Note: median = 0 for all airport terminals.",
                transform=ax.transAxes,
                ha="right",
                va="bottom",
                fontsize=7.6,
                color=COLOR_SECONDARY,
            )
        ax.set_xlabel("Travel-time saving (min)", fontsize=8.7, color=COLOR_BODY)
        ax.set_ylabel("")
        ax.grid(True, axis="x", color=COLOR_DIVIDER, linewidth=0.8)
        ax.grid(False, axis="y")
        ax.tick_params(axis="x", labelsize=8.3)

        x_max = max(float(part["mean_saving_min"].max()), float(part["median_saving_min"].max()), 0.2)
        ax.set_xlim(0.0, x_max * 1.12)
        ax.axvline(0.0, color=COLOR_SECONDARY, linewidth=0.9, linestyle=(0, (2, 2)), alpha=0.65, zorder=2)

    legend_handles = [
        Patch(facecolor=COLOR_BUS_MEAN, edgecolor="none", label="Bus mean"),
        Patch(facecolor=COLOR_BUS_MEDIAN, edgecolor="none", label="Bus median"),
        Patch(facecolor=COLOR_MRT_MEAN, edgecolor="none", label="MRT mean"),
        Patch(facecolor=COLOR_MRT_MEDIAN, edgecolor="none", label="MRT median"),
    ]
    fig.legend(
        handles=legend_handles,
        loc="lower center",
        ncol=4,
        frameon=False,
        fontsize=8.3,
        bbox_to_anchor=(0.5, 0.01),
    )

    fig.subplots_adjust(left=0.17, right=0.985, top=0.88, bottom=0.14, wspace=0.45)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, facecolor="white")
    plt.close(fig)


def group_stats(series: pd.Series) -> Dict[str, Any]:
    s = _clean_saving_series(series)
    improved = s[s > 0]
    n_total = int(len(s))
    n_improved = int((s > 0).sum())
    n_unchanged = int((s == 0).sum())
    return {
        "n_total": n_total,
        "improved_n_pct": f"{n_improved} ({(n_improved / n_total * 100):.1f}%)" if n_total else "0 (0.0%)",
        "unchanged_n_pct": f"{n_unchanged} ({(n_unchanged / n_total * 100):.1f}%)" if n_total else "0 (0.0%)",
        "saving_mean": round(float(s.mean()), 3) if n_total else 0.0,
        "saving_median": round(float(s.median()), 3) if n_total else 0.0,
        "saving_p90": round(float(np.percentile(s, 90)), 3) if n_total else 0.0,
        "saving_max": round(float(s.max()), 3) if n_total else 0.0,
        "saving_mean_improved_only": round(float(improved.mean()), 3) if len(improved) else 0.0,
        "saving_median_improved_only": round(float(improved.median()), 3) if len(improved) else 0.0,
        "saving_p90_improved_only": round(float(np.percentile(improved, 90)), 3) if len(improved) else 0.0,
    }


def build_od_saving_summary_rows(df: pd.DataFrame) -> List[Dict[str, Any]]:
    groups = {
        "Overall": _clean_saving_series(df["saving_min"]),
        "CBD-bound": _clean_saving_series(df.loc[df["destination_group"] == "CBD-bound", "saving_min"]),
        "Airport-bound": _clean_saving_series(df.loc[df["destination_group"] == "Airport-bound", "saving_min"]),
    }
    stats = {name: group_stats(series) for name, series in groups.items()}

    rows: List[Dict[str, Any]] = []
    for label, key in OD_SUMMARY_ROW_ORDER:
        if key is None:
            rows.append({"Metric": label, "Overall": "", "CBD-bound": "", "Airport-bound": ""})
        else:
            rows.append({
                "Metric": label,
                "Overall": stats["Overall"][key],
                "CBD-bound": stats["CBD-bound"][key],
                "Airport-bound": stats["Airport-bound"][key],
            })
    return rows


def build_destination_terminal_summary_rows(dest_df: pd.DataFrame) -> List[Dict[str, Any]]:
    display_df = dest_df.sort_values(["destination_group", "rank_within_group"], ascending=[True, True]).copy()

    rows: List[Dict[str, Any]] = []
    for _, row in display_df.iterrows():
        rows.append({
            "Destination group": row["destination_group"],
            "Rank": int(row["rank_within_group"]),
            "Station name": row["station_name"],
            "Station type": row["station_type"],
            "Mean saving (min)": row["mean_saving_min"],
            "Median saving (min)": row["median_saving_min"],
            "90th percentile saving (min)": row["p90_saving_min"],
            "Maximum saving (min)": row["max_saving_min"],
            "Improved origins, n (%)": f'{int(row["improved_origins_n"])} ({row["improved_origins_pct"] * 100:.1f}%)',
            "Origins aggregated (N)": int(row["n_origins"]),
            "Terminal node ID": row["sink_id"],
            "Sink set": row["sink_set"],
        })
    return rows


def build_summary_4_3(cfg: Dict[str, Any], project_root: Path) -> Dict[str, str]:
    df = load_comparison_df(cfg, project_root)
    summary_dir = project_root / "analysis" / "summary"

    od_saving_cdf_path = summary_dir / "od_travel_time_saving_cdf_abc.png"
    origin_aggregated_saving_cdf_path = summary_dir / "origin_aggregated_mean_saving_cdf_ab.png"
    od_saving_summary_csv_path = summary_dir / "od_travel_time_saving_summary.csv"
    od_saving_summary_json_path = summary_dir / "od_travel_time_saving_summary_raw.json"

    destination_terminal_saving_bar_path = summary_dir / "destination_terminal_mean_median_saving_bar_ab.png"
    destination_terminal_summary_csv_path = summary_dir / "destination_terminal_saving_summary.csv"
    destination_terminal_summary_json_path = summary_dir / "destination_terminal_saving_summary_raw.json"

    create_od_travel_time_saving_cdf(df, od_saving_cdf_path)
    create_origin_aggregated_saving_cdf(df, origin_aggregated_saving_cdf_path)

    od_summary_rows = build_od_saving_summary_rows(df)
    save_csv(od_saving_summary_csv_path, od_summary_rows)
    save_json(od_saving_summary_json_path, od_summary_rows)

    terminal_lookup = load_destination_terminal_lookup(cfg, project_root)
    destination_terminal_df = build_destination_terminal_df(df, terminal_lookup)
    create_destination_terminal_saving_bar(destination_terminal_df, destination_terminal_saving_bar_path)

    destination_terminal_summary_rows = build_destination_terminal_summary_rows(destination_terminal_df)
    save_csv(destination_terminal_summary_csv_path, destination_terminal_summary_rows)
    save_json(destination_terminal_summary_json_path, destination_terminal_df.to_dict(orient="records"))

    return {
        "destination_terminal_mean_median_saving_bar_png": str(destination_terminal_saving_bar_path.relative_to(project_root)),
        "destination_terminal_saving_summary_csv": str(destination_terminal_summary_csv_path.relative_to(project_root)),
        "destination_terminal_saving_summary_json": str(destination_terminal_summary_json_path.relative_to(project_root)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Section 4.3 summary outputs")
    parser.add_argument("--project-root", type=Path, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg = runtime_cfg_for_comparison(CONFIG, ["pre_ring", "post_ring"])
    root = project_root_from(cfg, args.project_root)
    outputs = build_summary_4_3(cfg, root)
    for key, value in outputs.items():
        print(f"{key}: {value}")
