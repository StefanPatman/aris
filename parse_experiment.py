import sys
from collections import defaultdict
from dataclasses import dataclass, field

import matplotlib.pyplot as plt
import statistics


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
        print("TIMES:".ljust(10), self.times)
        print()


# ---- CLI ARGUMENTS ----

input_file = sys.argv[1]
output_file = sys.argv[2] if len(sys.argv) > 2 else None

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

# ---- PARSE ----

with open(input_file, "r") as f:
    data = defaultdict(lambda: Experiment())
    config = ""

    for line in f:
        if line.startswith("### RUN:"):
            parts = line.split()
            idx = parts.index("--map-by")
            config = parts[idx + 1].strip()
            data[config].config = config

        if line.startswith("CPU cores used:"):
            parts = line.split(": ")
            data[config].cores = parts[1].strip()

        if line.startswith("NUMA nodes used:"):
            parts = line.split(": ")
            data[config].numas = parts[1].strip()

        if line.strip().startswith("Time in seconds ="):
            parts = line.split("=")
            data[config].times.append(float(parts[1].strip()))

# ---- PRINTOUT ----

for x in data:
    data[x].print()

# ---- GROUPING ----

groups = defaultdict(list)

def get_base_and_variant(label: str):
    lines = label.split("\n")
    if len(lines) == 2:
        return lines[1], None
    elif len(lines) >= 3:
        return lines[1], lines[2]
    return label, None

for key, exp in data.items():
    if exp.times:
        display_name = NAME_MAP.get(exp.config, exp.config)
        base, variant = get_base_and_variant(display_name)
        median = statistics.median(exp.times)
        groups[base].append((variant, display_name, median))

# ---- ORDER ----

base_order = ["node", "socket", "numa", "CCD"]

# ---- PLOT ----

plt.figure(figsize=(6, 4))

bar_width = 0.35
group_gap = bar_width * 0.8

x_positions = []
labels = []
medians = []
colors = []

current_x = 0

for base in base_order:
    if base not in groups:
        continue

    group = groups[base]

    def sort_key(item):
        variant = item[0]
        if variant == "RR":
            return 0
        elif variant == "IO":
            return 1
        return 2

    group = sorted(group, key=sort_key)
    group_size = len(group)

    for i, (variant, label, median) in enumerate(group):
        offset = (i - (group_size - 1) / 2) * bar_width
        x_positions.append(current_x + offset)
        labels.append(label)
        medians.append(median)

        # Color logic
        if base == "node":
            colors.append("#007c98")
        else:
            if variant == "IO":
                colors.append("#c22f7d")
            else:
                colors.append("#007c98")

    extra_gap = group_gap
    if group_size == 1:
        extra_gap = group_gap * 2

    current_x += group_size * bar_width + extra_gap

# ---- DRAW ----

bars = plt.bar(x_positions, medians, width=bar_width, color=colors)

# Remove top and right spines (borders)
ax = plt.gca()
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

# Value labels
for bar in bars:
    height = bar.get_height()
    plt.text(
        bar.get_x() + bar.get_width() / 2,
        height,
        f"{height:.2f}",
        ha='center',
        va='bottom'
    )

plt.xticks(x_positions, labels)
# plt.xlabel("Configuration (map-by)")
# plt.ylabel("Execution Time (seconds)")
plt.tight_layout()

# ---- OUTPUT ----

if output_file:
    plt.savefig(output_file, bbox_inches='tight', transparent=True)
else:
    plt.show()