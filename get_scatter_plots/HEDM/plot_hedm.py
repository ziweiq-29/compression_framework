"""
Plot QoI vs bit rate for HEDM, aggregated over all available inputs.

Reads STANDARD/HEDM/*/<compressor>_standard.csv and pairs rows with
outputs/HEDM/<compressor>_hedm.csv using (compressor name, input, error_bound).
Keeps only run_all_compressors.py error_bounds (lines 21-33), then for each
(compressor x error_bound) computes arithmetic mean for every numeric metric.

Outputs are written into this folder: get_scatter_plots/HEDM/
"""
import sys
import os
import site

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
STANDARD_HEDM = os.path.join(BASE_DIR, "STANDARD", "HEDM")
HEDM_DIR = os.path.join(BASE_DIR, "HEDM")
PLOT_OUT = _SCRIPT_DIR

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
Y_EPSILON = 1e-12
SKIP_MEAN_KEYS = {"compressor name", "input", "error_bound"}


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


def list_standard_csvs(comp: str):
    out = []
    if not os.path.isdir(STANDARD_HEDM):
        return out
    for ds in sorted(os.listdir(STANDARD_HEDM)):
        p = os.path.join(STANDARD_HEDM, ds, f"{comp}_standard.csv")
        if os.path.isfile(p):
            out.append(p)
    return out


def merge_rows(std_rows, hedm_rows):
    hedm_by_key = {}
    for r in hedm_rows:
        k = (
            r.get("compressor name", "").strip(),
            r.get("input", "").strip(),
            _norm_eb(r.get("error_bound", "")),
        )
        hedm_by_key[k] = r

    merged = []
    for r in std_rows:
        k = (
            r.get("compressor name", "").strip(),
            r.get("input", "").strip(),
            _norm_eb(r.get("error_bound", "")),
        )
        if k in hedm_by_key:
            out = dict(r)
            out.update(hedm_by_key[k])
            merged.append(out)
    return merged


def gather_all_merged_rows():
    rows = []
    for comp in COMPRESSORS:
        hedm_csv = os.path.join(HEDM_DIR, f"{comp}_hedm.csv")
        if not os.path.isfile(hedm_csv):
            continue
        hedm_rows = read_csv(hedm_csv)
        for std_csv in list_standard_csvs(comp):
            std_rows = read_csv(std_csv)
            rows.extend(merge_rows(std_rows, hedm_rows))
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
        cr = to_float(r.get("compression_ratio"), default=0.0)
        r["bit_rate"] = (32.0 / cr) if cr and cr > 0 else np.nan


def aggregate_mean_by_compressor_and_eb(rows):
    groups = defaultdict(list)
    for r in rows:
        comp = r.get("compressor name", "").strip() or "default"
        eb_n = _norm_eb(r.get("error_bound", ""))
        if eb_n not in _ALLOWED_EB_NORM:
            continue
        groups[(comp, eb_n)].append(r)

    all_keys = set()
    for r in rows:
        all_keys.update(r.keys())

    mean_rows = []
    for (comp, eb_n), grp in sorted(groups.items(), key=lambda x: (x[0][0], float(x[0][1] or 0))):
        canon_eb = _EB_NORM_TO_CANON.get(eb_n, eb_n)
        out = {"compressor name": comp, "error_bound": canon_eb}
        for k in sorted(all_keys):
            if k in SKIP_MEAN_KEYS:
                continue
            vals = [to_float(r.get(k)) for r in grp]
            vals = [v for v in vals if np.isfinite(v)]
            if not vals:
                continue
            out[k] = float(np.mean(vals))
        mean_rows.append(out)

    mean_rows.sort(key=lambda r: (r.get("compressor name", ""), to_float(r.get("error_bound"), 0.0)))
    return mean_rows


def qoi_vs_bit_rate(plot_dir, rows, y_col, ylabel, filename, *, ylim=None, y_bottom=None):
    by_comp_points = {}
    for r in rows:
        comp = r.get("compressor name", "").strip() or "default"
        x = to_float(r.get("bit_rate"))
        y = to_float(r.get(y_col))
        if np.isnan(y) or np.isnan(x):
            continue
        if y <= 0:
            y = Y_EPSILON 
        by_comp_points.setdefault(comp, []).append((x, y))

    fig, ax = plt.subplots(figsize=(7, 6))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    color_cycle = plt.rcParams.get("axes.prop_cycle", None)
    default_colors = (color_cycle.by_key().get("color", []) if color_cycle else []) or [
        "tab:blue", "tab:orange", "tab:green", "tab:red", "tab:purple", "tab:brown"
    ]
    comp_names = sorted(by_comp_points.keys())
    comp_colors = {c: default_colors[i % len(default_colors)] for i, c in enumerate(comp_names)}

    for comp in comp_names:
        arr = np.asarray(by_comp_points[comp], dtype=np.float64)
        if arr.size == 0:
            continue
        ax.scatter(arr[:, 0], arr[:, 1], color=comp_colors[comp], alpha=0.55, s=24, label=comp)

    ax.set_xscale("log")
    ax.set_yscale("log")
    if ylim is not None:
        ax.set_ylim(*ylim)
    if y_bottom is not None:
        ax.set_ylim(bottom=float(y_bottom))
    ax.set_xlabel("Bit rate", fontsize=12, color="black")
    ax.set_ylabel(ylabel, fontsize=12, color="black")
    ax.tick_params(axis="both", labelsize=10, colors="black")
    for spine in ax.spines.values():
        spine.set_color("black")
    leg = ax.legend(fontsize=10)
    leg.get_frame().set_facecolor("white")
    for t in leg.get_texts():
        t.set_color("black")
    ax.grid(False)
    fig.tight_layout(pad=1.2)
    out = os.path.join(plot_dir, filename)
    fig.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print(f"Saved {out}")


def scatter_xy_by_compressor(plot_dir, rows, x_col, y_col, xlabel, ylabel, filename):
    by_comp_points = {}
    for r in rows:
        comp = r.get("compressor name", "").strip() or "default"
        x = to_float(r.get(x_col))
        y = to_float(r.get(y_col))
        if np.isnan(x) or np.isnan(y):
            continue
        if y <= 0:
            y = Y_EPSILON
        by_comp_points.setdefault(comp, []).append((x, y))

    fig, ax = plt.subplots(figsize=(7, 6))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    color_cycle = plt.rcParams.get("axes.prop_cycle", None)
    default_colors = (color_cycle.by_key().get("color", []) if color_cycle else []) or [
        "tab:blue", "tab:orange", "tab:green", "tab:red", "tab:purple", "tab:brown"
    ]
    comp_names = sorted(by_comp_points.keys())
    comp_colors = {c: default_colors[i % len(default_colors)] for i, c in enumerate(comp_names)}

    for comp in comp_names:
        arr = np.asarray(by_comp_points[comp], dtype=np.float64)
        if arr.size == 0:
            continue
        ax.scatter(arr[:, 0], arr[:, 1], color=comp_colors[comp], alpha=0.7, s=24, label=comp)

    ax.set_xlabel(xlabel, fontsize=12, color="black")
    ax.set_ylabel(ylabel, fontsize=12, color="black")
    ax.set_yscale("log")
    ax.tick_params(axis="both", labelsize=10, colors="black")
    for spine in ax.spines.values():
        spine.set_color("black")
    leg = ax.legend(fontsize=10)
    leg.get_frame().set_facecolor("white")
    for t in leg.get_texts():
        t.set_color("black")
    ax.grid(False)
    fig.tight_layout(pad=1.2)
    out = os.path.join(plot_dir, filename)
    fig.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print(f"Saved {out}")


def main():
    os.makedirs(PLOT_OUT, exist_ok=True)

    rows = gather_all_merged_rows()
    if not rows:
        print("No merged HEDM rows found.")
        raise SystemExit(1)

    filtered = filter_by_error_bounds(rows)
    print(f"Rows before EB filter: {len(rows)}, after ({len(ERROR_BOUNDS)} bounds): {len(filtered)}")

    add_bit_rate(filtered)
    agg = aggregate_mean_by_compressor_and_eb(filtered)
    print(
        f"Aggregated points: {len(agg)} (compressors: "
        f"{sorted(set(r.get('compressor name', '').strip() for r in agg))})"
    )

    prefix = "hedm_mean_"
    qoi_vs_bit_rate(PLOT_OUT, agg, "wasserstein_distance", "Wasserstein distance", prefix + "wasserstein_vs_bit_rate.png")
    qoi_vs_bit_rate(
        PLOT_OUT,
        agg,
        "p99",
        "p99 Nearest-Neighbor Distance",
        prefix + "p99_vs_bit_rate.png",
        y_bottom=1e-4,
    )
    qoi_vs_bit_rate(
        PLOT_OUT,
        agg,
        "p90",
        "p90 Nearest-Neighbor Distance",
        prefix + "p90_vs_bit_rate.png",
        y_bottom=1e-4,
    )

    scatter_xy_by_compressor(
        PLOT_OUT, agg, "psnr", "wasserstein_distance", "PSNR (dB)", "Wasserstein distance", prefix + "wasserstein_vs_psnr.png"
    )
    scatter_xy_by_compressor(
        PLOT_OUT, agg, "ssim", "wasserstein_distance", "SSIM", "Wasserstein distance", prefix + "wasserstein_vs_ssim.png"
    )
    scatter_xy_by_compressor(
        PLOT_OUT, agg, "psnr", "p90", "PSNR (dB)", "p90 Nearest-Neighbor Distance", prefix + "p90_vs_psnr.png"
    )
    scatter_xy_by_compressor(
        PLOT_OUT, agg, "ssim", "p90", "SSIM", "p90 Nearest-Neighbor Distance", prefix + "p90_vs_ssim.png"
    )

    print("\nAll plots saved under", PLOT_OUT)


if __name__ == "__main__":
    main()
