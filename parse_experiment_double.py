#!/usr/bin/env python3

import argparse
import re
import statistics
from dataclasses import dataclass, field

import matplotlib.pyplot as plt

TIME_RE = re.compile(r'Time in seconds\s*=\s*([0-9.]+)')

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
            times = effective_times(proc)
            en = len(times)
            median_indices = set()
            if en:
                order = sorted(range(en), key=lambda i: times[i])
                mid = en // 2
                median_indices = {order[mid]} if en % 2 else {order[mid - 1], order[mid]}
            discard_idx = n - 1 if proc.discard_last and n else None
            times_str = ' '.join(
                f'{t:.2f}-' if i == discard_idx else
                f'{t:.2f}*' if i in median_indices else f'{t:.2f}'
                for i, t in enumerate(proc.times)
            )
            print(f"  {label} {proc.bench} ({n} runs)")
            print(f"    CORES: {proc.cores}")
            print(f"    TIMES: {times_str}")
        print()

# ---- PLOT HELPERS ----

BASE_ORDER = ['node', 'socket', 'numa', 'ccd']
BAR_WIDTH = 0.35
GROUP_GAP = BAR_WIDTH * 0.8

def config_parts(config):
    parts = config.split('_')
    base = parts[1] if len(parts) > 1 else config
    variant = parts[2] if len(parts) > 2 else ''
    return base, variant

def build_plot_data(segments, proc_attr):
    groups = {}
    for cd in segments:
        base, variant = config_parts(cd.config)
        proc = getattr(cd, proc_attr)
        if not proc.times:
            continue
        label = f"half\n{base}\n{variant}"
        stat = statistics.median(effective_times(proc))
        groups.setdefault(base, []).append((variant, label, stat, proc.times))

    x_positions, labels, stats, colors, scatter_points = [], [], [], [], []
    current_x = 0

    for base in BASE_ORDER:
        if base not in groups:
            continue
        group = sorted(groups[base], key=lambda item: 0 if item[0] == 'RR' else 1)
        n = len(group)
        for i, (variant, label, stat, times) in enumerate(group):
            x = current_x + (i - (n - 1) / 2) * BAR_WIDTH
            x_positions.append(x)
            labels.append(label)
            stats.append(stat)
            scatter_points.append((x, times))
            colors.append('#c22f7d' if variant == 'IO' else '#007c98')
        current_x += n * BAR_WIDTH + (GROUP_GAP if n > 1 else GROUP_GAP * 2)

    return x_positions, labels, stats, colors, scatter_points

def draw_subplot(ax, x_positions, labels, stats, colors, scatter_points, title, mode):
    bars = ax.bar(x_positions, stats, width=BAR_WIDTH, color=colors)
    if mode == 'dots':
        for x, times in scatter_points:
            ax.scatter([x] * len(times), times, color='black', s=14, zorder=3)
    elif mode == 'boxplot':
        cap_width = BAR_WIDTH * 0.4
        for x, times in scatter_points:
            lo, hi = min(times), max(times)
            ax.plot([x, x], [lo, hi], color='black', linewidth=1.5, zorder=3)
            ax.plot([x - cap_width / 2, x + cap_width / 2], [hi, hi], color='black', linewidth=1.5, zorder=3)
            ax.plot([x - cap_width / 2, x + cap_width / 2], [lo, lo], color='black', linewidth=1.5, zorder=3)
    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h, f'{h:.2f}',
                ha='center', va='bottom', fontsize=8)
    ax.set_xticks(x_positions)
    ax.set_xticklabels(labels)
    ax.set_title(title)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

# ---- MAIN ----

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('jobid')
    parser.add_argument('output_file', nargs='?', default=None)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-b', '--bars-only', action='store_true',
                        help='plain median bars only, no dots or box plot')
    group.add_argument('-d', '--dots', action='store_true',
                        help='show a dot per individual measurement on top of '
                             'the median bars, instead of a box plot')
    return parser.parse_args()

def main():
    args = parse_args()

    segments = parse_out(f'{args.jobid}.out')

    print_segments(segments)

    mode = 'bars' if args.bars_only else ('dots' if args.dots else 'boxplot')

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))

    for ax, proc_attr, bench_label in [(ax1, 'proc1', 'BENCH 1'), (ax2, 'proc2', 'BENCH 2')]:
        xp, lbl, stats, col, pts = build_plot_data(segments, proc_attr)
        bench_name = getattr(segments[0], proc_attr).bench if segments else ''
        draw_subplot(ax, xp, lbl, stats, col, pts, f'{bench_label}: {bench_name}', mode)

    plt.tight_layout()

    if args.output_file:
        plt.savefig(args.output_file, bbox_inches='tight', transparent=True)
    else:
        plt.show()

if __name__ == '__main__':
    main()
