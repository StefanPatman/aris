#!/usr/bin/env python3

import argparse
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field

import matplotlib.pyplot as plt

from bench_common import (
    add_plot_mode_args,
    draw_grouped_bars,
    enable_click_cursor,
    layout_bars,
    median_indices,
    plot_mode_from_args,
    save_or_show,
)

TIME_RE = re.compile(r'Time in seconds\s*=\s*([0-9.]+)')

BASE_ORDER = ['node', 'socket', 'numa', 'ccd']


@dataclass
class ProcData:
    bench: str = ""
    cores: str = ""
    numas: str = ""
    times: list = field(default_factory=list)
    discard_last: bool = False


def effective_times(proc):
    if proc.discard_last and proc.times:
        return proc.times[:-1]
    return proc.times


@dataclass
class ConfigData:
    config: str = ""
    proc1: ProcData = field(default_factory=ProcData)
    proc2: ProcData = field(default_factory=ProcData)


# ---- PARSE ----

def parse_out(filename):
    segments = []
    with open(filename) as f:
        lines = [l.rstrip('\n') for l in f]

    i = 0
    while i < len(lines):
        if not lines[i].startswith('# RUN:'):
            i += 1
            continue

        parts = lines[i].split()
        cd = ConfigData(config=parts[2])
        cd.proc1.bench = parts[3] if len(parts) > 3 else ''
        cd.proc2.bench = parts[4] if len(parts) > 4 else ''

        section = None
        i += 1
        while i < len(lines) and not lines[i].startswith('# RUN:'):
            l = lines[i].strip()
            if l == '## REPORT 1:':
                section = 'report1'
            elif l == '## REPORT 2:':
                section = 'report2'
            elif l == '## BENCH 1:':
                section = 'bench1'
            elif l == '## BENCH 2:':
                section = 'bench2'
            elif l.startswith('## '):
                section = None
            else:
                if section == 'report1':
                    if l.startswith('CPU cores used:'):
                        cd.proc1.cores = l.split(':', 1)[1].strip()
                    elif l.startswith('NUMA nodes used:'):
                        cd.proc1.numas = l.split(':', 1)[1].strip()
                elif section == 'report2':
                    if l.startswith('CPU cores used:'):
                        cd.proc2.cores = l.split(':', 1)[1].strip()
                    elif l.startswith('NUMA nodes used:'):
                        cd.proc2.numas = l.split(':', 1)[1].strip()
                elif section in ('bench1', 'bench2'):
                    m = TIME_RE.search(lines[i])
                    if m:
                        t = float(m.group(1))
                        (cd.proc1 if section == 'bench1' else cd.proc2).times.append(t)
            i += 1

        if len(cd.proc1.times) > len(cd.proc2.times):
            cd.proc1.discard_last = True
        elif len(cd.proc2.times) > len(cd.proc1.times):
            cd.proc2.discard_last = True

        segments.append(cd)
    return segments


# ---- CONSOLE OUTPUT ----

def print_segments(segments):
    for cd in segments:
        print(f"# RUN: {cd.config} | {cd.proc1.bench} vs {cd.proc2.bench}")
        for label, proc in [('BENCH_1', cd.proc1), ('BENCH_2', cd.proc2)]:
            n = len(proc.times)
            medians = median_indices(effective_times(proc))
            discard_idx = n - 1 if proc.discard_last and n else None
            times_str = ' '.join(
                f'{t:.2f}-' if i == discard_idx else
                f'{t:.2f}*' if i in medians else f'{t:.2f}'
                for i, t in enumerate(proc.times)
            )
            print(f"  {label} {proc.bench} ({n} runs)")
            print(f"    CORES: {proc.cores}")
            print(f"    TIMES: {times_str}")
        print()


# ---- GROUPING / PLOT DATA ----

def config_parts(config):
    parts = config.split('_')
    base = parts[1] if len(parts) > 1 else config
    variant = parts[2] if len(parts) > 2 else ''
    return base, variant


def build_plot_data(segments, proc_attr):
    groups = defaultdict(list)
    for cd in segments:
        base, variant = config_parts(cd.config)
        proc = getattr(cd, proc_attr)
        if not proc.times:
            continue
        label = f"half\n{base}\n{variant}"
        times = effective_times(proc)
        stat = statistics.median(times)
        groups[base].append((variant, label, stat, times))

    return layout_bars(BASE_ORDER, groups)


def draw_subplot(ax, x_positions, items, title, mode):
    draw_grouped_bars(ax, x_positions, items, mode, fontsize=8)
    ax.set_title(title)


# ---- MAIN ----

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('jobid')
    parser.add_argument('output_file', nargs='?', default=None)
    add_plot_mode_args(parser)
    return parser.parse_args()


def main():
    args = parse_args()

    segments = parse_out(f'{args.jobid}.out')

    print_segments(segments)

    mode = plot_mode_from_args(args)

    bench1_name = segments[0].proc1.bench if segments else ''
    bench2_name = segments[0].proc2.bench if segments else ''
    same_bench = bench1_name == bench2_name

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4), sharey=same_bench)

    for ax, proc_attr, bench_label, bench_name in [
        (ax1, 'proc1', 'BENCH 1', bench1_name),
        (ax2, 'proc2', 'BENCH 2', bench2_name),
    ]:
        xp, items = build_plot_data(segments, proc_attr)
        draw_subplot(ax, xp, items, f'{bench_label}: {bench_name}', mode)

    enable_click_cursor(fig, (ax1, ax2))

    plt.tight_layout()

    save_or_show(args.output_file)


if __name__ == '__main__':
    main()
