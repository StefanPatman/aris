#!/usr/bin/env python3

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

# ---- STYLE ----

COLOR_RR = "#007c98"
COLOR_IO = "#c22f7d"
COLOR_DEFAULT = "#8a8a8a"

BAR_WIDTH = 0.35
GROUP_GAP = BAR_WIDTH * 0.8


def variant_color(variant):
    if variant == "RR":
        return COLOR_RR
    if variant == "IO":
        return COLOR_IO
    return COLOR_DEFAULT


def variant_sort_key(variant):
    return {"RR": 0, "IO": 1}.get(variant, 2)


# ---- NAME MAP (single-node style experiments) ----

SINGLE_NODE_NAME_MAP = {
    "ppr:64:socket": "half\nnode",
    "socket": "half\nsocket\nRR",
    "ppr:32:socket": "half\nsocket\nIO",
    "numa": "half\nnuma\nRR",
    "ppr:8:numa": "half\nnuma\nIO",
    "L3cache": "half\nCCD\nRR",
    "ppr:4:L3cache": "half\nCCD\nIO",
}


# ---- TIMES ----

def median_indices(times):
    n = len(times)
    if not n:
        return set()
    order = sorted(range(n), key=lambda i: times[i])
    mid = n // 2
    return {order[mid]} if n % 2 else {order[mid - 1], order[mid]}


def format_times(times, fmt="{:.2f}"):
    marked = median_indices(times)
    return " ".join(
        f"{fmt.format(t)}*" if i in marked else fmt.format(t)
        for i, t in enumerate(times)
    )


# ---- LABELS ----

def split_label(label, standalone_prefixes=()):
    """Split a "\n"-joined NAME_MAP label into (base, variant).

    e.g. "half\nnode\nRR" -> ("node", "RR"), "half\nnode" -> ("node", None).
    Labels whose first line is in standalone_prefixes are kept whole as
    their own base, e.g. "full\nnode" -> ("full\nnode", None).
    """
    lines = label.split("\n")
    if lines[0] in standalone_prefixes:
        return label, None
    if len(lines) == 1:
        return label, None
    if len(lines) == 2:
        return lines[1], None
    return lines[1], lines[2]


# ---- GROUPING / LAYOUT ----

def layout_bars(base_order, groups, bar_width=BAR_WIDTH, group_gap=GROUP_GAP):
    """Assign x-positions to grouped bar items.

    groups: dict[base] -> list of items, where item[0] is the variant
    ("RR", "IO", or None). Within each base, items are ordered RR, then
    IO, then others. Groups are laid out left to right in base_order,
    with a gap between groups (a wider gap for single-bar groups).

    Returns (x_positions, ordered_items), aligned index-for-index.
    """
    x_positions = []
    ordered_items = []
    current_x = 0

    for base in base_order:
        if base not in groups:
            continue

        group = sorted(groups[base], key=lambda item: variant_sort_key(item[0]))
        n = len(group)

        for i, item in enumerate(group):
            x_positions.append(current_x + (i - (n - 1) / 2) * bar_width)
            ordered_items.append(item)

        current_x += n * bar_width + (group_gap if n > 1 else group_gap * 2)

    return x_positions, ordered_items


# ---- PLOTTING ----

def style_axes(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def annotate_bars(ax, bars, fmt="{:.2f}", **text_kwargs):
    text_kwargs.setdefault("ha", "center")
    text_kwargs.setdefault("va", "bottom")
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, height, fmt.format(height), **text_kwargs)


def save_or_show(output_file):
    if output_file:
        plt.savefig(output_file, bbox_inches="tight", transparent=True)
    else:
        plt.show()


def enable_click_cursor(fig, axes, color="red"):
    """Draw a horizontal line spanning the whole figure at the clicked
    y-position, so bar heights can be compared across subplots. The line
    is replaced on each subsequent click. Only has an effect with an
    interactive backend (i.e. when the figure is shown via plt.show(),
    not saved straight to a file).
    """
    state = {"line": None}

    def on_click(event):
        if event.inaxes not in axes or event.y is None:
            return
        if state["line"] is not None:
            state["line"].remove()
        y_fig = fig.transFigure.inverted().transform((0, event.y))[1]
        state["line"] = fig.add_artist(
            Line2D([0, 1], [y_fig, y_fig], transform=fig.transFigure,
                   color=color, linewidth=1, linestyle="--", zorder=5)
        )
        fig.canvas.draw_idle()

    fig.canvas.mpl_connect("button_press_event", on_click)


def draw_grouped_bars(ax, x_positions, items, mode="bars", annotate_fmt="{:.2f}", **annotate_kwargs):
    """Draw one grouped-bar plot on ax.

    items: list of (variant, label, value, raw_values), aligned with
    x_positions. `value` sets the bar height; `raw_values` (a list of
    numbers) is used by the 'dots' and 'whiskers' modes:
      - 'bars':     plain median/value bars only
      - 'dots':     a dot per entry in raw_values, on top of the bars
      - 'whiskers': a min-max range line (with caps), on top of the bars
    """
    labels = [item[1] for item in items]
    values = [item[2] for item in items]
    colors = [variant_color(item[0]) for item in items]

    bars = ax.bar(x_positions, values, width=BAR_WIDTH, color=colors)

    if mode == "dots":
        for x, item in zip(x_positions, items):
            raw = item[3]
            ax.scatter([x] * len(raw), raw, color="black", s=14, zorder=3)
    elif mode == "whiskers":
        cap_width = BAR_WIDTH * 0.4
        for x, item in zip(x_positions, items):
            raw = item[3]
            if not raw:
                continue
            lo, hi = min(raw), max(raw)
            ax.plot([x, x], [lo, hi], color="black", linewidth=1.5, zorder=3)
            ax.plot([x - cap_width / 2, x + cap_width / 2], [hi, hi], color="black", linewidth=1.5, zorder=3)
            ax.plot([x - cap_width / 2, x + cap_width / 2], [lo, lo], color="black", linewidth=1.5, zorder=3)

    annotate_bars(ax, bars, fmt=annotate_fmt, **annotate_kwargs)
    ax.set_xticks(x_positions)
    ax.set_xticklabels(labels)
    style_axes(ax)
    return bars


# ---- CLI ----

def add_plot_mode_args(parser):
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-w", "--whiskers", action="store_true",
                        help="show a min-max range line (with caps) on top of the bars")
    group.add_argument("-d", "--dots", action="store_true",
                        help="show a dot per individual measurement on top of the bars")
    return parser


def plot_mode_from_args(args):
    if args.whiskers:
        return "whiskers"
    if args.dots:
        return "dots"
    return "bars"
