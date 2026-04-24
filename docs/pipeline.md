# Processing pipeline

This document records the file-processing relationships used by the project. The aim is to make the repository auditable: every derived output should be traceable to raw inputs, configuration settings, and a script stage.

## Pipeline overview

```text
raw/bus/bus_route.json
        ↓
scripts/raw/build_bus_base.py
        ↓
model/base/bus_base.json

raw/mrt/mrt_route_topology.json
raw/mrt/mrt_links.json
raw/mrt/mrt_transfer_stations.json
raw/mrt/mrt_station_alignment/LTAMRTStation_topology_station_points_manual_rules.geojson
        ↓
scripts/raw/build_mrt_base.py
        ↓
model/base/mrt_base.json
        ↓
        ├── pre_ring: baseline copy
        │       ↓
        │   model/scenario/pre_ring/mrt_base.json
        │
        └── post_ring: apply CC ring overlay
                ↓
            model/scenario/post_ring/mrt_base.json
```

After scenario-specific MRT bases are created, both scenarios follow the same processing chain.

```text
model/base/bus_base.json
model/scenario/<scenario>/mrt_base.json
raw/spatial/refactored centroids.geojson
        ↓
scripts/intermodal/build_intermodal_base.py
        ↓
model/scenario/<scenario>/intermodal_base.json

raw/spatial/CBD_Bus.geojson
raw/spatial/CBD_MRT.geojson
raw/spatial/Airport_Bus.geojson
model/scenario/<scenario>/graph/nodes.json
        ↓
scripts/scenario/build_terminal_sets.py
        ↓
model/scenario/<scenario>/terminal_sets.json

model/base/bus_base.json
model/scenario/<scenario>/mrt_base.json
model/scenario/<scenario>/intermodal_base.json
        ↓
scripts/graph/build_nodes_from_base.py
scripts/graph/build_links_from_base.py
        ↓
model/scenario/<scenario>/graph/nodes.json
model/scenario/<scenario>/graph/links.json

model/scenario/<scenario>/graph/nodes.json
model/scenario/<scenario>/graph/links.json
model/scenario/<scenario>/terminal_sets.json
        ↓
scripts/analysis/build_od_shortest_paths.py
        ↓
analysis/scenario/<scenario>/od/centroid_terminal_shortest_paths.json
```

Scenario comparison then combines the pre-ring and post-ring results.

```text
analysis/scenario/pre_ring/od/centroid_terminal_shortest_paths.json
analysis/scenario/post_ring/od/centroid_terminal_shortest_paths.json
        ↓
scripts/analysis/compare_od_shortest_paths.py
        ↓
analysis/comparison/pre_vs_post_ring_od_shortest_paths.json
        ↓
        ├── scripts/analysis/build_path_restructuring_analysis.py
        │       ↓
        │   analysis/comparison/path_restructuring/summary.json
        │   analysis/comparison/path_restructuring/od_path_restructuring.json
        │
        ├── scripts/analysis/build_network_incidence_delta.py
        │       ↓
        │   analysis/comparison/network_incidence/*.csv
        │   analysis/comparison/network_incidence/summary.json
        │
        ├── scripts/analysis/build_summary_4_3.py
        │       ↓
        │   analysis/summary/*.csv
        │   analysis/summary/*.xlsx
        │   analysis/summary/*.png
        │
        └── scripts/analysis/build_origin_impact_payload.py
                ↓
            analysis/origin_impact/*.csv
            analysis/origin_impact/origin_dashboard_payload.json
                ↓
            scripts/analysis/build_origin_spatial_visualization.py
            scripts/analysis/build_origin_impact_dashboard.py
                ↓
            analysis/visualization/*.png
            analysis/visualization/*.html
```

MRT station centrality is computed separately from the full multimodal graph. It uses a simplified physical-station MRT graph to isolate the rail-network mechanism.

```text
model/scenario/<scenario>/mrt_base.json
        ↓
scripts/analysis/build_mrt_station_centrality.py
        ↓
analysis/scenario/<scenario>/network/mrt_station_centrality.json

analysis/scenario/pre_ring/network/mrt_station_centrality.json
analysis/scenario/post_ring/network/mrt_station_centrality.json
        ↓
scripts/analysis/compare_mrt_station_centrality.py
        ↓
analysis/comparison/pre_vs_post_ring_mrt_station_centrality.csv
analysis/comparison/pre_vs_post_ring_mrt_station_centrality.json
```

## Stage input-output table

| Stage | Script | Main inputs | Main outputs |
|---|---|---|---|
| `build_bus_base` | `scripts/raw/build_bus_base.py` | `raw/bus/bus_route.json` | `model/base/bus_base.json` |
| `build_mrt_base` | `scripts/raw/build_mrt_base.py` | MRT topology, link, transfer, station-point files | `model/base/mrt_base.json` |
| `build_scenario_mrt_base` | `scripts/scenario/build_scenario_mrt_base.py` | base MRT, scenario overlay | scenario MRT base |
| `build_mrt_station_centrality` | `scripts/analysis/build_mrt_station_centrality.py` | scenario MRT base | scenario centrality JSON |
| `build_intermodal_base` | `scripts/intermodal/build_intermodal_base.py` | bus base, scenario MRT, centroids | scenario intermodal base |
| `build_terminal_sets` | `scripts/scenario/build_terminal_sets.py` | destination GeoJSON files, graph nodes | scenario terminal sets |
| `build_nodes_from_base` | `scripts/graph/build_nodes_from_base.py` | base and scenario files | scenario graph nodes |
| `build_links_from_base` | `scripts/graph/build_links_from_base.py` | base and scenario files | scenario graph links |
| `build_od_shortest_paths` | `scripts/analysis/build_od_shortest_paths.py` | graph, terminals | OD shortest-path JSON |
| `compare_mrt_station_centrality` | `scripts/analysis/compare_mrt_station_centrality.py` | scenario centrality JSON files | centrality comparison CSV and JSON |
| `compare_od_shortest_paths` | `scripts/analysis/compare_od_shortest_paths.py` | pre/post OD path JSON files | OD comparison JSON |
| `build_path_restructuring_analysis` | `scripts/analysis/build_path_restructuring_analysis.py` | OD comparison, graph lookups | path restructuring summary and audit JSON |
| `build_network_incidence_delta` | `scripts/analysis/build_network_incidence_delta.py` | OD comparison, graph lookups | station, line, segment incidence tables |
| `build_summary_4_3` | `scripts/analysis/build_summary_4_3.py` | OD comparison | report-ready tables and figures |
| `build_origin_impact_payload` | `scripts/analysis/build_origin_impact_payload.py` | OD comparison, clipped grids | origin and destination aggregation payloads |
| `build_origin_spatial_visualization` | `scripts/analysis/build_origin_spatial_visualization.py` | origin payload and grids | origin-side heatmap PNG |
| `build_origin_impact_dashboard` | `scripts/analysis/build_origin_impact_dashboard.py` | origin dashboard payload | self-contained HTML dashboard |
| `write_run_metadata` | `scripts/analysis/write_run_metadata.py` | configuration and generated outputs | `analysis/run_metadata.json` |

## Scenario-branching logic

Scenario branching starts before `build_intermodal_base` because the post-ring MRT stations can change centroid-to-MRT access links and bus-to-MRT transfer pairs. As a result, `intermodal_base.json`, graph nodes, graph links, terminal sets, and OD shortest paths are stored separately for `pre_ring` and `post_ring`.

## Generated-file policy

The files in `model/` and `analysis/` are generated outputs. They are useful for inspection and report production, but the reproducible source of the project is the combination of `raw/`, `scripts/`, `config.py`, and this pipeline definition. Large generated JSON files are excluded by `.gitignore` because they can be rebuilt.
