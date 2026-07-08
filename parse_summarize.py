#!/usr/bin/env python3

import argparse
import glob
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field

import matplotlib.pyplot as plt

from bench_common import (
    SINGLE_NODE_NAME_MAP as NAME_MAP,
    add_plot_mode_args,
    draw_grouped_bars,
    layout_bars,
    plot_mode_from_args,
    save_or_show,
    split_label,
)

BASELINE_KEY = "ppr:64:socket"  # half-node
BASE_ORDER = ["socket", "numa", "CCD"]


@dataclass
class Experiment:
    config: str = ""
    cores: str = ""
    numas: str = ""
    times: list[float] = field(default_factory=list)


# ---- PARSE ----

def parse_file(path):
    data = defaultdict(Experiment)
    config = ""

    with open(path) as f:
        for line in f:
            if line.startswith("# RUN:"):
                parts = line.split()
                try:
                    idx = parts.index("--map-by")
                except ValueError:
                    config = ""
                    continue
                config = parts[idx + 1].strip()
                data[config].config = config
                continue

            if not config:
                continue

            if line.startswith("CPU cores used:"):
                data[config].cores = line.split(": ", 1)[1].strip()
            elif line.startswith("NUMA nodes used:"):
                data[config].numas = line.split(": ", 1)[1].strip()
            elif line.strip().startswith("Time in seconds ="):
                data[config].times.append(float(line.split("=", 1)[1].strip()))

    return data


# ---- SPEEDUPS ----

def collect_speedups(files):
    speedups = defaultdict(list)

    for path in files:
        data = parse_file(path)

        if BASELINE_KEY not in data or not data[BASELINE_KEY].times:
            print(f"  Warning: baseline config not found in {path}, skipping.")
            continue

        baseline_median = statistics.median(data[BASELINE_KEY].times)

        for key, exp in data.items():
            if key == BASELINE_KEY or key not in NAME_MAP or not exp.times:
                continue
            config_median = statistics.median(exp.times)
            speedups[key].append(baseline_median / config_median)

    return speedups


# ---- GROUPING ----

def build_groups(speedups):
    groups = defaultdict(list)
    for key, sp_list in speedups.items():
        display_name = NAME_MAP[key]
        base, variant = split_label(display_name)
        avg = statistics.mean(sp_list)
        groups[base].append((variant, display_name, avg, sp_list))
    return groups


# ---- PLOT ----

def plot(groups, output_file, mode):
    x_positions, items = layout_bars(BASE_ORDER, groups)

    plt.figure(figsize=(6, 4))
    ax = plt.gca()
    draw_grouped_bars(ax, x_positions, items, mode, annotate_fmt="{:.2f}x", fontsize=8)
    ax.axhline(y=1.0, color="gray", linestyle="--", linewidth=0.8)
    ax.set_ylabel("Speedup over half-node")
    plt.tight_layout()

    save_or_show(output_file)


# ---- MAIN ----

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("glob_pattern")
    parser.add_argument("output_file", nargs="?", default=None)
    add_plot_mode_args(parser)
    args = parser.parse_args()

    files = sorted(glob.glob(args.glob_pattern, recursive=True))
    if not files:
        print(f"No files matched: {args.glob_pattern}")
        sys.exit(1)

    print(f"Found {len(files)} file(s).")

    speedups = collect_speedups(files)
    groups = build_groups(speedups)
    plot(groups, args.output_file, plot_mode_from_args(args))

    if args.output_file:
        print(f"Saved to {args.output_file}")


if __name__ == "__main__":
    main()
