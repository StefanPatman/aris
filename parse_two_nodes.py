#!/usr/bin/env python3

import argparse
import statistics
from collections import defaultdict
from dataclasses import dataclass, field

import matplotlib.pyplot as plt

from bench_common import (
    SINGLE_NODE_NAME_MAP,
    add_plot_mode_args,
    draw_grouped_bars,
    format_times,
    layout_bars,
    plot_mode_from_args,
    save_or_show,
    split_label,
)

NAME_MAP = {
    **SINGLE_NODE_NAME_MAP,
    "ppr:128:node": "full\nnode",
    "ppr:64:node": "half\nnode\nIO",
    "node": "half\nnode\nRR",
}

BASE_ORDER = ["full\nnode", "node", "socket", "numa", "CCD"]


@dataclass
class Experiment:
    config: str = ""
    alias: str = ""
    cores: dict = field(default_factory=dict)  # node_name -> cores string
    numas: dict = field(default_factory=dict)  # node_name -> numas string
    times: list[float] = field(default_factory=list)

    def print(self):
        w = 15

        def wrap_cores(cores_str, chunk=32):
            nums = cores_str.split()
            lines = [" ".join(nums[i:i + chunk]) for i in range(0, len(nums), chunk)]
            return ("\n" + " " * (w + 1)).join(lines)

        print("CONFIG:".ljust(w), self.config)
        print("ALIAS:".ljust(w), self.alias.replace("\n", " / "))
        for node in self.cores:
            print(f"[{node}] CORES:".ljust(w), wrap_cores(self.cores[node]))
            print(f"[{node}] NUMAS:".ljust(w), self.numas.get(node, ""))
        print("TIMES:".ljust(w), format_times(self.times))
        print()


# ---- PARSE ----

def parse_file(path):
    data = defaultdict(Experiment)
    config = ""
    current_node = None

    with open(path) as f:
        for line in f:
            if line.startswith("# RUN:"):
                parts = line.split()
                idx = parts.index("--map-by")
                config = parts[idx + 1].strip()
                data[config].config = config
                data[config].alias = NAME_MAP.get(config, config)
                current_node = None

            elif line.startswith("----- NODE:"):
                current_node = line.split(":")[1].strip().rstrip(" -").strip()

            elif line.startswith("CPU cores used:"):
                key = current_node or "_"
                data[config].cores[key] = line.split(": ", 1)[1].strip()

            elif line.startswith("NUMA nodes used:"):
                key = current_node or "_"
                data[config].numas[key] = line.split(": ", 1)[1].strip()

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
        base, variant = split_label(display_name, standalone_prefixes=("full",))
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
