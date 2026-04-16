"""
Plot QoI vs bit rate for FIDELITY, fixed to dataset folder a11c8.

Merges:
- outputs/STANDARD/FIDELITY/a11c8/<compressor>_fidelity.csv
- outputs/FIDELITY/a11c8/<compressor>_fidelity.csv

Then keeps run_all_compressors.py error_bounds and computes arithmetic mean per
(compressor x error_bound) for all numeric metrics. Scatter plots are saved under:
get_scatter_plots/FIDELITY/outputs/
"""
import sys
import os
import site

# keep user/venv package preference (same style as other plotting scripts)
if sys.prefix != sys.base_prefix:
    _venv_site = os.path.join(
        sys.prefix, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages"
    )
    if os.path.isdir(_venv_site):
        sys.path.insert(0, _venv_site)
        _prefix_abs = os.path.abspath(sys.prefix)
        sys.path = [p for p in sys.path if "site-packages" not in p or _prefix_abs in os.path.abspath(p)]

_user_site = ""
try:
    _user_site = site.getusersitepackages()
except Exception:
    _user_site = ""
if _user_site:
    _user_site_abs = os.path.abspath(_user_site)
    if os.path.isdir(_user_site_abs):
        sys.path = [p for p in sys.path if os.path.abspath(p) != _user_site_abs]
        sys.path.insert(0, _user_site_abs)

import csv
from collections import defaultdict
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BASE_CF = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))
BASE_DIR = os.path.join(_BASE_CF, "outputs")
TARGET_DATASET = "a11c8"
STANDARD_DIR = os.path.join(BASE_DIR, "STANDARD", "FIDELITY", TARGET_DATASET)
FIDELITY_DIR = os.path.join(BASE_DIR, "FIDELITY", TARGET_DATASET)
PLOT_OUT = os.path.join(_SCRIPT_DIR, "outputs")

# Same order / set as run_all_compressors.py lines 21-33
ERROR_BOUNDS = [
    "1e-6",
    "5e-6",
    "1e-5",
    "5e-5",
    "1e-4",
    "5e-4",
    "1e-3",
    "5e-3",
    "1e-2",
    "5e-2",
    "1e-1",
]

COMPRESSORS = ["sz3", "zfp", "sperr", "mgard"]
Y_EPSILON = 1e-18
SKIP_MEAN_KEYS = {"folder", "compressor", "compressor name", "input", "error_bound", "error_option"}


def _norm_eb(s: str) -> str:
    t = (s or "").strip()
    if not t:
        return ""
    try:
        return f"{float(t):.12g}"
    except (ValueError, TypeError):
        return t


_EB_NORM_TO_CANON = {_norm_eb(eb): eb for eb in ERROR_BOUNDS}
_ALLOWED_EB_NORM = set(_EB_NORM_TO_CANON.keys())


def read_csv(path):
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_float(x, default=np.nan):
    if x is None or (isinstance(x, str) and x.strip() in ("", "<empty>")):
        return default
    try:
        return float(x)
    except (ValueError, TypeError):
        return default


def normalize_row_keys(row):
    out = dict(row)
    # Unify compressor key names between files
    if "compressor" in out and "compressor name" not in out:
        out["compressor name"] = out.get("compressor", "")
    return out


def merge_rows(std_rows, fidelity_rows):
    fid_by_key = {}
    for r0 in fidelity_rows:
        r = normalize_row_keys(r0)
        key = (
            r.get("compressor name", "").strip(),
            _norm_eb(r.get("error_bound", "")),
        )
        fid_by_key[key] = r

    merged = []
    for r0 in std_rows:
        r = normalize_row_keys(r0)
        key = (
            r.get("compressor name", "").strip(),
            _norm_eb(r.get("error_bound", "")),
        )
        if key in fid_by_key:
            out = dict(r)
            out.update(fid_by_key[key])
            merged.append(out)
    return merged


def gather_all_merged_rows():
    rows = []
    for comp in COMPRESSORS:
        std_csv = os.path.join(STANDARD_DIR, f"{comp}_fidelity.csv")
        fid_csv = os.path.join(FIDELITY_DIR, f"{comp}_fidelity.csv")
        if not os.path.isfile(std_csv) or not os.path.isfile(fid_csv):
            continue
        rows.extend(merge_rows(read_csv(std_csv), read_csv(fid_csv)))
    return rows


def filter_by_error_bounds(rows):
    out = []
    for r in rows:
        eb_n = _norm_eb(r.get("error_bound", ""))
        if eb_n in _ALLOWED_EB_NORM:
            out.append(r)
    return out


def add_bit_rate(rows):
    for r in rows:
        # STANDARD/FIDELITY provides compression_ratio_npy
        cr = to_float(r.get("compression_ratio_npy"), default=np.nan)
        if np.isnan(cr) or cr <= 0:
            cr = to_float(r.get("compression_ratio"), default=np.nan)
        r["bit_rate"] = (32.0 / cr) if np.isfinite(cr) and cr > 0 else np.nan


def aggregate_mean_by_compressor_and_eb(rows):
    groups = defaultdict(list)
    for r in rows:
        comp = (r.get("compressor name", "") or r.get("compressor", "")).strip() or "default"
        eb_n = _norm_eb(r.get("error_bound", ""))
        if eb_n not in _ALLOWED_EB_NORM:
            continue
        groups[(comp, eb_n)].append(r)

    all_keys = set()
    for r in rows:
        all_keys.update(r.keys())

    mean_rows = []
    for (comp, eb_n), grp in sorted(groups.items(), key=lambda x: (x[0][0], float(x[0][1] or 0))):
        out = {"compressor name": comp, "error_bound": _EB_NORM_TO_CANON.get(eb_n, eb_n)}
        for k in sorted(all_keys):
            if k in SKIP_MEAN_KEYS:
                continue
            vals = [to_float(r.get(k)) for r in grp]
            vals = [v for v in vals if np.isfinite(v)]
            if vals:
                out[k] = float(np.mean(vals))
        mean_rows.append(out)

    mean_rows.sort(key=lambda r: (r.get("compressor name", ""), to_float(r.get("error_bound"), 0.0)))
    return mean_rows


def qoi_vs_bit_rate(
    plot_dir,
    rows,
    y_col,
    ylabel,
    filename,
    *,
    log_y=True,
    one_minus_y=False,
    plot_kind="scatter",
):
    by_comp_points = {}
    for r in rows:
        comp = r.get("compressor name", "").strip() or "default"
        x = to_float(r.get("bit_rate"))
        y = to_float(r.get(y_col))
        if np.isnan(y) or np.isnan(x):
            continue
        if one_minus_y:
            y = 1.0 - y
        if log_y and y <= 0:
            y = Y_EPSILON
        by_comp_points.setdefault(comp, []).append((x, y))

    fig, ax = plt.subplots(figsize=(7, 6))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    color_cycle = plt.rcParams.get("axes.prop_cycle", None)
    default_colors = (color_cycle.by_key().get("color", []) if color_cycle else []) or [
        "tab:blue", "tab:orange", "tab:green", "tab:red", "tab:purple", "tab:brown"
    ]
    # Fix compressor->color mapping across all plots.
    extra_comps = sorted([c for c in by_comp_points.keys() if c not in COMPRESSORS])
    ordered_comps = [c for c in COMPRESSORS if c in by_comp_points] + extra_comps
    comp_colors = {c: default_colors[i % len(default_colors)] for i, c in enumerate(COMPRESSORS)}
    for i, comp in enumerate(extra_comps):
        comp_colors[comp] = default_colors[(len(COMPRESSORS) + i) % len(default_colors)]

    # Fix compressor->line/marker mapping across all plots.
    linestyle_cycle = ["-", "--", "-.", ":"]
    marker_cycle = ["o", "^", "s", "D", "v", "P", "X", "*"]
    comp_linestyles = {c: linestyle_cycle[i % len(linestyle_cycle)] for i, c in enumerate(COMPRESSORS)}
    comp_markers = {c: marker_cycle[i % len(marker_cycle)] for i, c in enumerate(COMPRESSORS)}
    for i, comp in enumerate(extra_comps):
        comp_linestyles[comp] = linestyle_cycle[(len(COMPRESSORS) + i) % len(linestyle_cycle)]
        comp_markers[comp] = marker_cycle[(len(COMPRESSORS) + i) % len(marker_cycle)]

    for comp in ordered_comps:
        pts = by_comp_points[comp]
        if not pts:
            continue
        arr = np.asarray(pts, dtype=np.float64)
        if arr.size == 0:
            continue

        xx = arr[:, 0]
        yy = arr[:, 1]
        color = comp_colors[comp]

        if plot_kind == "scatter":
            ax.scatter(xx, yy, color=color, alpha=0.55, s=24, label=comp.upper())
        elif plot_kind == "line":
            # This plot uses log-x, so filter non-positive x values.
            pos_mask = np.isfinite(xx) & (xx > 0) & np.isfinite(yy)
            xx = xx[pos_mask]
            yy = yy[pos_mask]
            if xx.size == 0:
                continue
            order = np.argsort(xx)
            ax.plot(
                xx[order],
                yy[order],
                color=color,
                alpha=0.9,
                linewidth=1.6,
                linestyle=comp_linestyles.get(comp, "-"),
                marker=comp_markers.get(comp, "o"),
                markersize=4.5,
                label=comp.upper(),
            )
        else:
            raise ValueError(f"Unknown plot_kind={plot_kind!r} (expected 'scatter' or 'line')")

    ax.set_xscale("log")
    if log_y:
        ax.set_yscale("log")
    ax.set_xlabel("Bit rate", fontsize=25, color="black")
    ax.set_ylabel(ylabel, fontsize=25, color="black")
    ax.tick_params(axis="both", labelsize=18, colors="black")
    for spine in ax.spines.values():
        spine.set_color("black")
    leg = ax.legend(fontsize=25)
    leg.get_frame().set_facecolor("white")
    for t in leg.get_texts():
        t.set_color("black")
    ax.set_axisbelow(True)
    # Draw gridlines only at major ticks (where axis has numeric labels).
    ax.grid(True, axis="both", which="major", linestyle="--", alpha=0.35)
    fig.tight_layout(pad=1.2)
    out = os.path.join(plot_dir, filename)
    fig.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print(f"Saved {out}")


def scatter_xy_by_compressor(
    plot_dir, rows, x_col, y_col, xlabel, ylabel, filename, *, log_y=True, one_minus_y=False
):
    by_comp_points = {}
    for r in rows:
        comp = r.get("compressor name", "").strip() or "default"
        x = to_float(r.get(x_col))
        y = to_float(r.get(y_col))
        if np.isnan(x) or np.isnan(y):
            continue
        if one_minus_y:
            y = 1.0 - y
        if log_y and y <= 0:
            y = Y_EPSILON
        by_comp_points.setdefault(comp, []).append((x, y))

    fig, ax = plt.subplots(figsize=(7, 6))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    color_cycle = plt.rcParams.get("axes.prop_cycle", None)
    default_colors = (color_cycle.by_key().get("color", []) if color_cycle else []) or [
        "tab:blue", "tab:orange", "tab:green", "tab:red", "tab:purple", "tab:brown"
    ]
    # Fix compressor->color mapping across all plots.
    extra_comps = sorted([c for c in by_comp_points.keys() if c not in COMPRESSORS])
    ordered_comps = [c for c in COMPRESSORS if c in by_comp_points] + extra_comps
    comp_colors = {c: default_colors[i % len(default_colors)] for i, c in enumerate(COMPRESSORS)}
    for i, comp in enumerate(extra_comps):
        comp_colors[comp] = default_colors[(len(COMPRESSORS) + i) % len(default_colors)]

    for comp in ordered_comps:
        arr = np.asarray(by_comp_points[comp], dtype=np.float64)
        if arr.size == 0:
            continue
        ax.scatter(arr[:, 0], arr[:, 1], color=comp_colors[comp], alpha=0.7, s=24, label=comp.upper())

    ax.set_xlabel(xlabel, fontsize=25, color="black")
    ax.set_ylabel(ylabel, fontsize=25, color="black")
    if log_y:
        ax.set_yscale("log")
    ax.tick_params(axis="both", labelsize=18, colors="black")
    for spine in ax.spines.values():
        spine.set_color("black")
    leg = ax.legend(fontsize=25)
    leg.get_frame().set_facecolor("white")
    for t in leg.get_texts():
        t.set_color("black")
    ax.set_axisbelow(True)
    # Draw gridlines only at major ticks (where axis has numeric labels).
    ax.grid(True, axis="both", which="major", linestyle="--", alpha=0.35)
    fig.tight_layout(pad=1.2)
    out = os.path.join(plot_dir, filename)
    fig.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print(f"Saved {out}")


def main():
    os.makedirs(PLOT_OUT, exist_ok=True)

    if not os.path.isdir(STANDARD_DIR) or not os.path.isdir(FIDELITY_DIR):
        print(f"Missing input directories:\\n  {STANDARD_DIR}\\n  {FIDELITY_DIR}")
        raise SystemExit(1)

    raw = gather_all_merged_rows()
    if not raw:
        print("No merged rows found for FIDELITY/a11c8.")
        raise SystemExit(1)

    filtered = filter_by_error_bounds(raw)
    add_bit_rate(filtered)
    rows = aggregate_mean_by_compressor_and_eb(filtered)

    print(f"Rows before EB filter: {len(raw)}, after ({len(ERROR_BOUNDS)} bounds): {len(filtered)}")
    print(f"Aggregated points: {len(rows)}")

    prefix = "fidelity_a11c8_mean_"
    qoi_vs_bit_rate(PLOT_OUT, rows, "wasserstein_distance", "Wasserstein distance", prefix + "wasserstein_vs_bit_rate.png")
    qoi_vs_bit_rate(PLOT_OUT, rows, "p99", "p99", prefix + "p99_vs_bit_rate.png")
    qoi_vs_bit_rate(PLOT_OUT, rows, "p90", "p90", prefix + "p90_vs_bit_rate.png")

    # Fidelity is very close to 1; use (1 - fidelity) on log scale to separate points.
    qoi_vs_bit_rate(
        PLOT_OUT,
        rows,
        "fidelity",
        "1-Fidelity",
        prefix + "one_minus_fidelity_vs_bit_rate.png",
        log_y=True,
        one_minus_y=True,
        plot_kind="line",
    )

    scatter_xy_by_compressor(
        PLOT_OUT,
        rows,
        "psnr_magnitude",
        "wasserstein_distance",
        "PSNR magnitude (dB)",
        "Wasserstein distance",
        prefix + "wasserstein_vs_psnr_magnitude.png",
    )
    scatter_xy_by_compressor(
        PLOT_OUT,
        rows,
        "psnr_magnitude",
        "p90",
        "PSNR magnitude (dB)",
        "p90",
        prefix + "p90_vs_psnr_magnitude.png",
    )
    scatter_xy_by_compressor(
        PLOT_OUT,
        rows,
        "psnr_magnitude",
        "fidelity",
        "PSNR magnitude (dB)",
        "1-Fidelity",
        prefix + "fidelity_vs_psnr_magnitude.png",
        log_y=True,
        one_minus_y=True,
    )

    print("\nAll plots saved under", PLOT_OUT)


if __name__ == "__main__":
    main()
