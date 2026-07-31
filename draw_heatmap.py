#!/usr/bin/env python3

import argparse
import csv

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import TwoSlopeNorm

from bench_common import save_or_show

MAX_COLS = 4

# Cap on the figure size (inches) so the interactive window fits on screen;
# larger layouts are scaled down preserving their aspect ratio.
MAX_FIG_WIDTH = 14
MAX_FIG_HEIGHT = 7.5

CONFIG_ORDER = [
    "half_node_RR", "half_node_IO",
    "half_socket_RR", "half_socket_IO",
    "half_numa_RR", "half_numa_IO",
    "half_ccd_RR", "half_ccd_IO",
]

# There is no RR-mapped single-node run to compare half_node_RR against,
# so its speedups (present e.g. in node-baseline tables) are never drawn;
# its CONFIG_ORDER slot stays reserved but empty.
EXCLUDED_CONFIGS = {"half_node_RR"}


# ---- PARSE ----

def parse_speedups(path):
    """Read the tab-separated speedup table and return
    ({config: {(main, colocated): speedup}}, benches, (lo, hi)), with
    configs and benches in order of first appearance. (lo, hi) is the
    speedup range over the WHOLE file, so heatmaps of different configs
    share one color scale and can be compared.
    """
    configs = {}
    benches = []
    all_speedups = []

    with open(path) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row["configuration"] in EXCLUDED_CONFIGS:
                continue
            main, colocated = row["main process"], row["colocated process"]
            for bench in (main, colocated):
                if bench not in benches:
                    benches.append(bench)
            speedup = float(row["speedup"])
            configs.setdefault(row["configuration"], {})[(main, colocated)] = speedup
            all_speedups.append(speedup)

    if not configs:
        raise SystemExit(f"No speedup rows in {path}")
    return configs, benches, (min(all_speedups), max(all_speedups))


def layout_configs(configs):
    """Order configs canonically, inserting a placeholder (None) for
    known configs missing from the file (e.g. half_node_RR, which the
    speedup tables omit) so grid positions stay aligned. Placeholders
    are only inserted up to the last config present; unknown configs
    keep their file order at the end.
    """
    known = [c for c in CONFIG_ORDER if c in configs]
    if not known:
        return dict(configs)
    last = CONFIG_ORDER.index(known[-1])
    ordered = {c: configs.get(c) for c in CONFIG_ORDER[:last + 1]}
    ordered.update((c, cells) for c, cells in configs.items() if c not in CONFIG_ORDER)
    return ordered


def build_matrix(cells, benches):
    data = np.full((len(benches), len(benches)), np.nan)
    for (main, colocated), speedup in cells.items():
        data[benches.index(main), benches.index(colocated)] = speedup
    return data


# ---- CONSOLE OUTPUT ----

def print_matrix(data, benches, config):
    print(f"# CONFIG: {config}")
    width = max(max(len(b) for b in benches), 4) + 2
    print("".ljust(width) + "".join(b.ljust(width) for b in benches))
    for i, bench in enumerate(benches):
        cells = "".join(
            ("-" if np.isnan(v) else f"{v:.2f}").ljust(width) for v in data[i]
        )
        print(bench.ljust(width) + cells)


# ---- PLOT ----

def draw_config(ax, data, benches, config, norm):
    n = len(benches)
    im = ax.imshow(data, cmap="RdBu", norm=norm)

    # Matplotlib's default cursor formatter overflows on hover with
    # TwoSlopeNorm (fixed upstream in 3.5.2); format the value ourselves.
    im.format_cursor_data = (
        lambda value: "" if np.ma.is_masked(value) or np.isnan(value) else f"[{value:.4f}]"
    )

    for i in range(n):
        for j in range(n):
            value = data[i, j]
            if np.isnan(value):
                continue
            r, g, b, _ = im.cmap(im.norm(value))
            ink = "black" if 0.299 * r + 0.587 * g + 0.114 * b > 0.5 else "white"
            ax.text(j, i, f"{value:.2f}", ha="center", va="center", color=ink)

    ax.set_xticks(range(n))
    ax.set_xticklabels(benches)
    ax.set_yticks(range(n))
    ax.set_yticklabels(benches)
    ax.set_title(config)

    ax.set_xticks(np.arange(-0.5, n), minor=True)
    ax.set_yticks(np.arange(-0.5, n), minor=True)
    ax.grid(which="minor", color="white", linewidth=2)
    ax.tick_params(which="minor", length=0)

    return im


def draw_heatmaps(matrices, benches, speedup_range, output_file):
    n = len(benches)
    lo, hi = speedup_range
    norm = TwoSlopeNorm(vcenter=1.0, vmin=min(lo, 0.95), vmax=max(hi, 1.05))

    n_cfg = len(matrices)
    ncols = min(n_cfg, MAX_COLS)
    nrows = (n_cfg + ncols - 1) // ncols

    width = (1.2 * n + 1.6) * ncols + 1
    height = (1.2 * n + 1) * nrows
    scale = min(1.0, MAX_FIG_WIDTH / width, MAX_FIG_HEIGHT / height)

    fig, axes = plt.subplots(nrows, ncols,
                             figsize=(width * scale, height * scale),
                             squeeze=False, layout="constrained")

    im = None
    for idx, (config, data) in enumerate(matrices.items()):
        ax = axes[idx // ncols][idx % ncols]
        if data is None:
            ax.set_visible(False)
            continue
        im = draw_config(ax, data, benches, config, norm)

    for ax in axes.flat[n_cfg:]:
        ax.set_visible(False)

    if n_cfg == 1:
        axes[0][0].set_ylabel("main process")
        axes[0][0].set_xlabel("colocated process")

    fig.colorbar(im, ax=axes, label="speedup", shrink=0.8)

    save_or_show(output_file)


# ---- MAIN ----

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("speedup_file", help="tab-separated speedup table, e.g. logs/speedups.tsv")
    parser.add_argument("config", nargs="?", default=None,
                         help='configuration to visualize, e.g. "half_numa_RR"; '
                              "omit to draw all configurations in one figure")
    parser.add_argument("-o", "--output", dest="output_file", default=None,
                         help="save the figure to this file instead of showing it")
    return parser.parse_args()


def main():
    args = parse_args()

    configs, benches, speedup_range = parse_speedups(args.speedup_file)
    if args.config:
        if args.config not in configs:
            raise SystemExit(f"No rows for configuration '{args.config}' in {args.speedup_file}. "
                             f"Available: {', '.join(configs)}")
        configs = {args.config: configs[args.config]}
    else:
        configs = layout_configs(configs)

    matrices = {
        config: build_matrix(cells, benches) if cells is not None else None
        for config, cells in configs.items()
    }

    for config, data in matrices.items():
        if data is None:
            continue
        print_matrix(data, benches, config)
        print()

    draw_heatmaps(matrices, benches, speedup_range, args.output_file)


if __name__ == "__main__":
    main()
