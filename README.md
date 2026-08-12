# Singapore Intermodal Public Transport Network Analysis

This repository documents a course project on multimodal public transport network modelling and scenario analysis. The project builds and compares two Singapore public transport network scenarios to evaluate the travel-time and path-restructuring effects of the Circle Line loop closure in the southern region.

The accompanying [Project Report](./Project%20Report.pdf) was submitted as part of the course project and provides the problem formulation, methodology, results, and discussion. This repository contains the corresponding implementation, data-processing workflow, and reproducible analysis pipeline.

## Project scope

The project evaluates centroid-to-terminal public transport travel from a southern residential study area to two destination groups: CBD terminals and Changi Airport terminals. The analysis uses a common directed, time-weighted multimodal graph for both scenarios and compares minimum-travel-time paths under identical origin, destination, and routing assumptions.

## Scenarios

- `pre_ring`: Circle Line before the CC29-CC30-CC31-CC32-CE2 closure.
- `post_ring`: Circle Line after the closure, with CC30 Keppel, CC31 Cantonment, CC32 Prince Edward Road, and eight directed MRT run links added at 2.0 minutes each.

A shared `base` layer is built once from raw data. Scenario-specific MRT, access, graph, centrality, shortest-path, and comparison outputs are then generated separately so that the pre-ring and post-ring results can coexist without overwriting each other.

## Key outputs

* `analysis/comparison/pre_vs_post_ring_mrt_station_centrality.json` — MRT station centrality changes.
* `analysis/comparison/pre_vs_post_ring_od_shortest_paths.json` — Detailed OD path comparison. *(Not uploaded.)*
* `analysis/comparison/path_restructuring/summary.json` — Optimal-path restructuring summary.
* `analysis/comparison/network_incidence/summary.json` — Network usage-pattern changes.
* `analysis/summary/od_travel_time_saving_summary.csv` — OD travel-time saving statistics.
* `analysis/summary/table_7_od_travel_time_saving_summary.xlsx` — Report-ready summary table.
* `analysis/visualization/origin_spatial_saving_heatmap_abc.png` — Spatial distribution of travel-time savings.
* `analysis/visualization/origin_impact_dashboard.html` — Interactive spatial impact dashboard.
* `analysis/run_metadata.json` — Run configuration and reproducibility metadata. *(Not uploaded.)*

## Quick start

The project was prepared for Python 3.12.5. The commands below create an isolated environment, install dependencies, and run the full pipeline.

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py --scenario all
```

### macOS or Linux

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py --scenario all
```

If `python3.12` is not available on macOS or Linux, use the local Python 3.12 executable name returned by `python3 --version` or install Python 3.12 first.

## Common run commands

Build both scenarios and all comparison outputs:

```bash
python main.py --scenario all
```

Build only the pre-ring scenario:

```bash
python main.py --scenario pre_ring
```

Build only the post-ring scenario:

```bash
python main.py --scenario post_ring
```

Run selected stages:

```bash
python main.py --scenario all --only compare_od_shortest_paths build_path_restructuring_analysis
```

Skip selected stages:

```bash
python main.py --scenario all --skip build_summary_4_3 build_origin_spatial_visualization
```

Validate one source centroid for one scenario:

```bash
python validate_shortest_paths.py --scenario post_ring --source G_000_003
```

## Pipeline design

Shared stages:

1. `build_bus_base`
2. `build_mrt_base`

Scenario stages:

1. `build_scenario_mrt_base`
2. `build_mrt_station_centrality`
3. `build_intermodal_base`
4. `build_terminal_sets`
5. `build_nodes_from_base`
6. `build_links_from_base`
7. `build_od_shortest_paths`

Comparison and reporting stages:

1. `compare_mrt_station_centrality`
2. `compare_od_shortest_paths`
3. `build_path_restructuring_analysis`
4. `build_network_incidence_delta`
5. `build_summary_4_3`
6. `build_origin_impact_payload`
7. `build_origin_spatial_visualization`
8. `build_origin_impact_dashboard`
9. `write_run_metadata`

A detailed input-output map is provided in `docs/pipeline.md`.

## Directory structure

```text
raw/                         raw and manually prepared input data
model/base/                  shared bus and MRT base files
model/scenario/pre_ring/     scenario-specific pre-ring files
model/scenario/post_ring/    scenario-specific post-ring files
analysis/scenario/pre_ring/  pre-ring analysis outputs
analysis/scenario/post_ring/ post-ring analysis outputs
analysis/comparison/         pre vs post comparison outputs
analysis/summary/            report-ready tables and figures
analysis/visualization/      dashboard and spatial visualizations
scripts/                     build and analysis scripts
docs/                        pipeline and data-source documentation
```

## Generated-file policy

Files under `model/` and `analysis/` are generated outputs. They can be rebuilt from `raw/`, `config.py`, and `scripts/` by running `python main.py --scenario all`. Large generated JSON files are useful for audit but do not need to be committed to a public repository unless the repository is intended to include complete computed outputs.

## Data sources

A file-level data-source inventory is provided in `docs/data_sources.md`. In brief, the project uses cleaned bus route data, bus stop spatial data, MRT topology and adjacent-station travel-time data, manually prepared CBD and airport terminal sets, southern-region grid centroids, and a scenario overlay for the new Circle Line stations and links.

If the optional MRT adjacent-time scraper is used, install Playwright browsers once with:

```bash
python -m playwright install chromium
```

## Dependencies

Install the required packages with:

```bash
pip install -r requirements.txt
```
