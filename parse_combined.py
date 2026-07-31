#!/usr/bin/env python3

import argparse
import glob
import os
import re

import matplotlib.pyplot as plt

import parse_double
import parse_single_node
from bench_common import (
    add_plot_mode_args,
    draw_grouped_bars,
    enable_click_cursor,
    layout_bars,
    plot_mode_from_args,
    save_or_show,
    split_label,
)

SINGLE_NODE_DIR = "logs/single_node"
COLOCATION_DIR = "logs/colocation"


# ---- LOCATE INPUT FILES ----

def _colo_candidates(bench1, bench2):
    """Yield (double_path, (cls1, size1), (cls2, size2), swapped) for every
    colocation .out file pairing bench1 with bench2, in either filename
    order. `swapped` is True when the file lists bench2 before bench1
    (so its proc1/proc2 are bench2/bench1 rather than bench1/bench2).
    """
    pattern = re.compile(
        rf"^{re.escape(bench1)}\.([A-Z])\.(\d+)-{re.escape(bench2)}\.([A-Z])\.(\d+)-\d+\.out$"
    )
    for path in glob.glob(os.path.join(COLOCATION_DIR, f"{bench1}.*-{bench2}.*.out")):
        m = pattern.match(os.path.basename(path))
        if m:
            yield path, (m.group(1), m.group(2)), (m.group(3), m.group(4)), False

    if bench1 == bench2:
        return

    pattern = re.compile(
        rf"^{re.escape(bench2)}\.([A-Z])\.(\d+)-{re.escape(bench1)}\.([A-Z])\.(\d+)-\d+\.out$"
    )
    for path in glob.glob(os.path.join(COLOCATION_DIR, f"{bench2}.*-{bench1}.*.out")):
        m = pattern.match(os.path.basename(path))
        if m:
            yield path, (m.group(3), m.group(4)), (m.group(1), m.group(2)), True


def find_cross_run(bench1, bench2):
    """Find the colocation run pairing bench1 with bench2 whose per-process
    class/size also has a matching single-node log, e.g. ("ep", "cg") ->
    logs/colocation/ep.E.64-cg.D.64-3.out, logs/single_node/ep.E.64.log,
    logs/single_node/cg.D.64.log.

    Returns (double_path, single_path1, single_path2, swapped), where
    swapped indicates the double file's proc1/proc2 are (bench2, bench1)
    rather than (bench1, bench2).
    """
    matches = []
    for double_path, (cls1, size1), (cls2, size2), swapped in _colo_candidates(bench1, bench2):
        single1 = os.path.join(SINGLE_NODE_DIR, f"{bench1}.{cls1}.{size1}.log")
        single2 = os.path.join(SINGLE_NODE_DIR, f"{bench2}.{cls2}.{size2}.log")
        if os.path.exists(single1) and os.path.exists(single2):
            matches.append((double_path, single1, single2, swapped))

    if not matches:
        raise SystemExit(f"No single-node + colocation run found for benchmarks '{bench1}' and '{bench2}'")
    if len(matches) > 1:
        paths = [m[0] for m in matches]
        raise SystemExit(f"Ambiguous match for '{bench1}' and '{bench2}': {paths}")

    return matches[0]


def find_runs(bench):
    """Find the (class, size) run that has both a single-node log and a
    self-colocated (bench vs bench) .out file for `bench`, e.g. "ep" ->
    logs/single_node/ep.E.64.log and logs/colocation/ep.E.64-ep.E.64-3.out.
    """
    double_path, single_path, _, _ = find_cross_run(bench, bench)
    return single_path, double_path


# ---- PLOT DATA ----

def build_single_plot_data(path):
    data = parse_single_node.parse_file(path)
    for exp in data.values():
        exp.print()
    groups = parse_single_node.build_groups(data)
    return layout_bars(parse_single_node.BASE_ORDER, groups)


def build_double_plot_data(path):
    segments = parse_double.parse_out(path)
    parse_double.print_segments(segments)
    return (
        parse_double.build_plot_data(segments, "proc1"),
        parse_double.build_plot_data(segments, "proc2"),
    )


# ---- SPEEDUP FILE ----

def _item_key(label):
    """Normalized (base, variant) key for a bar item's label, e.g.
    "half\nCCD\nRR" -> ("ccd", "RR"), "half\nnode" -> ("node", "")."""
    base, variant = split_label(label)
    return base.lower(), variant or ""


def speedup_rows(single_items, colo_items):
    """Compute (configuration, speedup) per colocation configuration, where
    speedup is single_node_time / colocated_time (using the per-config
    medians). The variant-less single-node "half node" run is an IO
    mapping, so it only pairs with half_node_IO; half_node_RR is skipped.
    """
    single = {_item_key(label): value for _, label, value, _ in single_items}

    rows = []
    for _, label, colo_time, _ in colo_items:
        base, variant = _item_key(label)
        if base == "node" and variant != "IO":
            continue
        single_time = single.get((base, variant), single.get((base, "")))
        config = f"half_{base}_{variant}" if variant else f"half_{base}"
        if single_time is None:
            print(f"warning: no single-node time for {config}, skipping speedup row")
            continue
        rows.append((config, single_time / colo_time))
    return rows


def average_rows(rows1, rows2):
    """Average two (configuration, speedup) row lists config-by-config."""
    other = dict(rows2)
    return [
        (config, (speedup + other[config]) / 2 if config in other else speedup)
        for config, speedup in rows1
    ]


def append_speedups(speedup_file, main_bench, secondary_bench, rows):
    """Append the (configuration, speedup) rows to the tab-separated
    speedup table: main process, secondary process, configuration, speedup.
    """
    write_header = not os.path.exists(speedup_file) or os.path.getsize(speedup_file) == 0
    with open(speedup_file, "a") as f:
        if write_header:
            f.write("main process\tsecondary process\tconfiguration\tspeedup\n")
        for config, speedup in rows:
            f.write(f"{main_bench}\t{secondary_bench}\t{config}\t{speedup:.4f}\n")


# ---- PLOTTING ----

def plot_single_bench(bench, output_file, mode, speedup_file=None):
    single_path, double_path = find_runs(bench)

    print(f"# SINGLE NODE: {single_path}")
    xp_single, items_single = build_single_plot_data(single_path)

    print(f"\n# COLOCATION: {double_path}")
    (xp_d1, items_d1), (xp_d2, items_d2) = build_double_plot_data(double_path)

    if speedup_file:
        rows = average_rows(speedup_rows(items_single, items_d1),
                            speedup_rows(items_single, items_d2))
        append_speedups(speedup_file, bench, bench, rows)

    fig, (ax_single, ax_d1, ax_d2) = plt.subplots(1, 3, figsize=(18, 4), sharey=True)

    draw_grouped_bars(ax_single, xp_single, items_single, mode)
    ax_single.set_title(f"Single node: {bench}")

    parse_double.draw_subplot(ax_d1, xp_d1, items_d1, f"Colocated (proc 1): {bench}", mode)
    parse_double.draw_subplot(ax_d2, xp_d2, items_d2, f"Colocated (proc 2): {bench}", mode)

    enable_click_cursor(fig, (ax_single, ax_d1, ax_d2))

    plt.tight_layout()

    save_or_show(output_file)


def plot_two_benches(bench1, bench2, output_file, mode, speedup_file=None):
    double_path, single_path1, single_path2, swapped = find_cross_run(bench1, bench2)
    bench1_attr, bench2_attr = ("proc2", "proc1") if swapped else ("proc1", "proc2")

    print(f"# SINGLE NODE: {single_path1}")
    xp_single1, items_single1 = build_single_plot_data(single_path1)

    print(f"\n# SINGLE NODE: {single_path2}")
    xp_single2, items_single2 = build_single_plot_data(single_path2)

    print(f"\n# COLOCATION: {double_path}")
    segments = parse_double.parse_out(double_path)
    parse_double.print_segments(segments)
    xp_d1, items_d1 = parse_double.build_plot_data(segments, bench1_attr)
    xp_d2, items_d2 = parse_double.build_plot_data(segments, bench2_attr)

    if speedup_file:
        append_speedups(speedup_file, bench1, bench2, speedup_rows(items_single1, items_d1))
        append_speedups(speedup_file, bench2, bench1, speedup_rows(items_single2, items_d2))

    fig, ((ax_single1, ax_d1), (ax_single2, ax_d2)) = plt.subplots(2, 2, figsize=(12, 8))
    ax_d1.sharey(ax_single1)
    ax_d2.sharey(ax_single2)

    draw_grouped_bars(ax_single1, xp_single1, items_single1, mode)
    ax_single1.set_title(f"Single node: {bench1}")
    parse_double.draw_subplot(ax_d1, xp_d1, items_d1, f"Colocated with {bench2}: {bench1}", mode)

    draw_grouped_bars(ax_single2, xp_single2, items_single2, mode)
    ax_single2.set_title(f"Single node: {bench2}")
    parse_double.draw_subplot(ax_d2, xp_d2, items_d2, f"Colocated with {bench1}: {bench2}", mode)

    enable_click_cursor(fig, (ax_single1, ax_d1, ax_single2, ax_d2))

    plt.tight_layout()

    save_or_show(output_file)


# ---- MAIN ----

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("bench", nargs="+", help='one benchmark, e.g. "ep", or two, e.g. "ep cg"')
    parser.add_argument("-o", "--output", dest="output_file", default=None,
                         help="save the figure to this file instead of showing it")
    parser.add_argument("-s", "--speedup-file", dest="speedup_file", default=None,
                         help="append per-configuration speedup rows (single_node_time / colocated_time) to this TSV file")
    add_plot_mode_args(parser)
    return parser.parse_args()


def main():
    args = parse_args()
    benches = args.bench
    mode = plot_mode_from_args(args)

    if len(benches) == 1:
        plot_single_bench(benches[0], args.output_file, mode, args.speedup_file)
    elif len(benches) == 2:
        plot_two_benches(benches[0], benches[1], args.output_file, mode, args.speedup_file)
    else:
        raise SystemExit('Provide one benchmark, e.g. "ep", or two, e.g. ep cg')


if __name__ == "__main__":
    main()
