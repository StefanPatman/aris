import sys
from collections import defaultdict
from dataclasses import dataclass, field

import matplotlib.pyplot as plt
import statistics


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
            lines = [" ".join(nums[i:i+chunk]) for i in range(0, len(nums), chunk)]
            return ("\n" + " " * (w + 1)).join(lines)

        print("CONFIG:".ljust(w), self.config)
        print("ALIAS:".ljust(w), self.alias.replace("\n", " / "))
        for node in self.cores:
            print(f"[{node}] CORES:".ljust(w), wrap_cores(self.cores[node]))
            print(f"[{node}] NUMAS:".ljust(w), self.numas.get(node, ""))
        print("TIMES:".ljust(w), self.times)
        print()


# ---- CLI ARGUMENTS ----

input_file = sys.argv[1]
output_file = sys.argv[2] if len(sys.argv) > 2 else None

# ---- RENAME MAP ----

NAME_MAP = {
    "ppr:128:node": "full\nnode",
    "ppr:64:node": "half\nnode\nIO",
    "node": "half\nnode\nRR",
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
    current_node = None

    for line in f:
        if line.startswith("### RUN:"):
            parts = line.split()
            idx = parts.index("--map-by")
            config = parts[idx + 1].strip()
            data[config].config = config
            data[config].alias = NAME_MAP.get(config, config)
            current_node = None

        if line.startswith("----- NODE:"):
            current_node = line.split(":")[1].strip().rstrip(" -").strip()

        if line.startswith("CPU cores used:"):
            key = current_node if current_node else "_"
            data[config].cores[key] = line.split(": ", 1)[1].strip()

        if line.startswith("NUMA nodes used:"):
            key = current_node if current_node else "_"
            data[config].numas[key] = line.split(": ", 1)[1].strip()

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
    if len(lines) == 1:
        return label, None
    elif len(lines) == 2:
        if lines[0] == "full":
            return label, None  # "full\nnode" is its own group key
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

base_order = ["full\nnode", "node", "socket", "numa", "CCD"]

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
        if base == "full\nnode":
            colors.append("#007c98")
        elif variant == "IO":
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