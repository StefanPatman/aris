#!/usr/bin/env python3

import argparse
import statistics
from collections import defaultdict
from dataclasses import dataclass, field

import matplotlib.pyplot as plt

from bench_common import (
    SINGLE_NODE_NAME_MAP as NAME_MAP,
    add_plot_mode_args,
    draw_grouped_bars,
    format_times,
    layout_bars,
    plot_mode_from_args,
    save_or_show,
    split_label,
)

BASE_ORDER = ["node", "socket", "numa", "CCD"]


@dataclass
class Experiment:
    config: str = ""
    cores: str = ""
    numas: str = ""
    times: list[float] = field(default_factory=list)

    def print(self):
        print("CONFIG:".ljust(10), self.config)
        print("CORES:".ljust(10), self.cores)
        print("NUMAS:".ljust(10), self.numas)
        print("TIMES:".ljust(10), format_times(self.times))
        print()


# ---- PARSE ----

def parse_file(path):
    data = defaultdict(Experiment)
    config = ""

    with open(path) as f:
        for line in f:
            if line.startswith("# RUN:"):
                parts = line.split()
                idx = parts.index("--map-by")
                config = parts[idx + 1].strip()
                data[config].config = config

            elif line.startswith("CPU cores used:"):
                data[config].cores = line.split(": ", 1)[1].strip()

            elif line.startswith("NUMA nodes used:"):
                data[config].numas = line.split(": ", 1)[1].strip()

            elif line.strip().startswith("Time in seconds ="):
                data[config].times.append(float(line.split("=", 1)[1].strip()))

    return data


# ---- GROUPING ----

def build_groups(data):
    groups = defaultdict(list)
    for exp in data.values():
        if not exp.times:
            continue
        display_name = NAME_MAP.get(exp.config, exp.config)
        base, variant = split_label(display_name)
        median = statistics.median(exp.times)
        groups[base].append((variant, display_name, median, exp.times))
    return groups


# ---- PLOT ----

def plot(groups, output_file, mode):
    x_positions, items = layout_bars(BASE_ORDER, groups)

    plt.figure(figsize=(6, 4))
    draw_grouped_bars(plt.gca(), x_positions, items, mode)
    plt.tight_layout()

    save_or_show(output_file)


# ---- MAIN ----

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file")
    parser.add_argument("output_file", nargs="?", default=None)
    add_plot_mode_args(parser)
    args = parser.parse_args()

    data = parse_file(args.input_file)

    for exp in data.values():
        exp.print()

    groups = build_groups(data)
    plot(groups, args.output_file, plot_mode_from_args(args))


if __name__ == "__main__":
    main()
