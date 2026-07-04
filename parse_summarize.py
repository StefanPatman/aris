import sys
import glob
import statistics
from collections import defaultdict
from dataclasses import dataclass, field

import matplotlib.pyplot as plt


@dataclass
class Experiment:
    config: str = ""
    cores: str = ""
    numas: str = ""
    times: list[float] = field(default_factory=list)


# ---- RENAME MAP ----

NAME_MAP = {
    "ppr:64:socket": "half\nnode",
    "socket": "half\nsocket\nRR",
    "ppr:32:socket": "half\nsocket\nIO",
    "numa": "half\nnuma\nRR",
    "ppr:8:numa": "half\nnuma\nIO",
    "L3cache": "half\nCCD\nRR",
    "ppr:4:L3cache": "half\nCCD\nIO",
}

BASELINE_KEY = "ppr:64:socket"  # half-node

# ---- PARSE ----

def parse_file(path):
    data = defaultdict(lambda: Experiment())
    config = ""

    with open(path, "r") as f:
        for line in f:
            if line.startswith("### RUN:"):
                parts = line.split()
                try:
                    idx = parts.index("--map-by")
                    config = parts[idx + 1].strip()
                    data[config].config = config
                except ValueError:
                    config = ""
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


# ---- CLI ----

if len(sys.argv) < 2:
    print("Usage: python summarize_experiments.py <glob_pattern> [output_file]")
    sys.exit(1)

glob_pattern = sys.argv[1]
output_file = sys.argv[2] if len(sys.argv) > 2 else None

files = sorted(glob.glob(glob_pattern, recursive=True))
if not files:
    print(f"No files matched: {glob_pattern}")
    sys.exit(1)

print(f"Found {len(files)} file(s).")

# ---- COLLECT SPEEDUPS ----

# speedups[config_key] = list of per-file speedup values
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

# ---- GROUPING ----

def get_base_and_variant(label):
    lines = label.split("\n")
    if len(lines) >= 3:
        return lines[1], lines[2]
    elif len(lines) == 2:
        return lines[1], None
    return label, None

def sort_key(item):
    variant = item[0]
    return 0 if variant == "RR" else 1 if variant == "IO" else 2

base_order = ["socket", "numa", "CCD"]

groups = defaultdict(list)
for key, sp_list in speedups.items():
    display_name = NAME_MAP[key]
    base, variant = get_base_and_variant(display_name)
    avg = statistics.mean(sp_list)
    std = statistics.stdev(sp_list) if len(sp_list) > 1 else 0.0
    groups[base].append((variant, display_name, avg, std))

# ---- BUILD PLOT DATA ----

bar_width = 0.35
group_gap = bar_width * 0.8

x_positions = []
labels = []
avgs = []
stds = []
colors = []

current_x = 0

for base in base_order:
    if base not in groups:
        continue

    group = sorted(groups[base], key=sort_key)
    group_size = len(group)

    for i, (variant, label, avg, std) in enumerate(group):
        offset = (i - (group_size - 1) / 2) * bar_width
        x_positions.append(current_x + offset)
        labels.append(label)
        avgs.append(avg)
        stds.append(std)
        colors.append("#c22f7d" if variant == "IO" else "#007c98")

    current_x += group_size * bar_width + (group_gap if group_size > 1 else group_gap * 2)

# ---- DRAW ----

plt.figure(figsize=(6, 4))

bars = plt.bar(
    x_positions, avgs,
    width=bar_width, color=colors,
    yerr=stds if any(s > 0 for s in stds) else None,
    capsize=4,
)

ax = plt.gca()
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.axhline(y=1.0, color='gray', linestyle='--', linewidth=0.8)

for bar in bars:
    height = bar.get_height()
    plt.text(
        bar.get_x() + bar.get_width() / 2,
        height,
        f"{height:.2f}x",
        ha='center', va='bottom', fontsize=8,
    )

plt.xticks(x_positions, labels)
plt.ylabel(f"Speedup over half-node")
plt.tight_layout()

# ---- OUTPUT ----

if output_file:
    plt.savefig(output_file, bbox_inches='tight', transparent=True)
    print(f"Saved to {output_file}")
else:
    plt.show()
