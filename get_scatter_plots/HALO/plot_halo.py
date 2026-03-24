"""
Plot QoI vs bit rate for HALO/NYX, aggregated over all dataset folders.

Reads every STANDARD/NYX/<dataset>/<comp>_standard.csv paired with
HALO/NYX/<dataset>/<comp>_halo.csv, keeps only rows whose error_bound is in the
same list as run_all_compressors.py (error_bounds), then for each
(compressor × error_bound) computes the arithmetic mean of every numeric column
across all matching rows (all files / datasets).

Scatter plots (same style as before) are written under get_scatter_plots/HALO/outputs/.
Uses only csv + numpy + matplotlib.
"""
import sys
import os
import site

# Ensure venv packages are used first (avoid system numpy 1.19.5 when loading matplotlib)
if sys.prefix != sys.base_prefix:
    _venv_site = os.path.join(
        sys.prefix, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages"
    )
    if os.path.isdir(_venv_site):
        sys.path.insert(0, _venv_site)
        _prefix_abs = os.path.abspath(sys.prefix)
        sys.path = [p for p in sys.path if "site-packages" not in p or _prefix_abs in os.path.abspath(p)]

# Prefer user-local site-packages (~/.local/...) ahead of system packages,
# so matplotlib/numpy come from the same location and avoid ABI/version mismatch.
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

# ================= paths =================
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# compression_framework/get_scatter_plots/HALO/plot_halo.py -> ../../outputs
_BASE_CF = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))
BASE_DIR = os.path.join(_BASE_CF, "outputs")
STANDARD_NYX = os.path.join(BASE_DIR, "STANDARD", "NYX")
HALO_NYX = os.path.join(BASE_DIR, "HALO", "NYX")
PLOT_OUT = os.path.join(_SCRIPT_DIR, "outputs")

# Same order / set as run_all_compressors.py lines 21–33
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

# Do not average these keys (identifiers / non-scalar QoI for this script)
SKIP_MEAN_KEYS = {
    "compressor name",
    "input",
    "error_bound",
}


def _norm_eb(s: str) -> str:
    t = (s or "").strip()
    if not t:
        return ""
    try:
        return f"{float(t):.12g}"
    except (ValueError, TypeError):
        return t


# normalized string -> display string from ERROR_BOUNDS
_EB_NORM_TO_CANON = {_norm_eb(eb): eb for eb in ERROR_BOUNDS}
_ALLOWED_EB_NORM = set(_EB_NORM_TO_CANON.keys())


def list_datasets():
    if not os.path.isdir(STANDARD_NYX):
        return []
    out = []
    for name in sorted(os.listdir(STANDARD_NYX)):
        std_dir = os.path.join(STANDARD_NYX, name)
        halo_dir = os.path.join(HALO_NYX, name)
        if not os.path.isdir(std_dir) or not os.path.isdir(halo_dir):
            continue
        has_any = any(
            os.path.isfile(os.path.join(std_dir, c + "_standard.csv"))
            and os.path.isfile(os.path.join(halo_dir, c + "_halo.csv"))
            for c in COMPRESSORS
        )
        if has_any:
            out.append(name)
    return out


def read_csv(path):
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def merge_rows(std_rows, halo_rows):
    halo_by_key = {}
    for r in halo_rows:
        k = (r.get("compressor name", "").strip(), r.get("error_bound", "").strip())
        halo_by_key[k] = r
    merged = []
    for r in std_rows:
        k = (r.get("compressor name", "").strip(), r.get("error_bound", "").strip())
        if k in halo_by_key:
            out = dict(r)
            out.update(halo_by_key[k])
            merged.append(out)
    return merged


def to_float(x, default=np.nan):
    if x is None or (isinstance(x, str) and x.strip() in ("", "<empty>")):
        return default
    try:
        return float(x)
    except (ValueError, TypeError):
        return default


def gather_all_merged_rows():
    """All merged (standard+halo) rows from every NYX dataset × compressor."""
    rows = []
    for dataset_var in list_datasets():
        for comp in COMPRESSORS:
            results_csv = os.path.join(STANDARD_NYX, dataset_var, comp + "_standard.csv")
            halo_csv = os.path.join(HALO_NYX, dataset_var, comp + "_halo.csv")
            if not os.path.isfile(results_csv) or not os.path.isfile(halo_csv):
                continue
            std_rows = read_csv(results_csv)
            halo_rows = read_csv(halo_csv)
            rows.extend(merge_rows(std_rows, halo_rows))
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
    """
    One synthetic row per (compressor, canonical error_bound): arithmetic mean
    of every numeric column across all input rows in that group.
    """
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


def qoi_vs_bit_rate(plot_dir, rows, y_col, ylabel, title, filename):
    by_comp_points = {}
    for r in rows:
        comp = r.get("compressor name", "").strip() or "default"
        x = to_float(r.get("bit_rate"))
        y = to_float(r.get(y_col))
        if np.isnan(y) or np.isnan(x):
            continue
        if y <= 0:
            y = Y_EPSILON
        if comp not in by_comp_points:
            by_comp_points[comp] = []
        by_comp_points[comp].append((x, y))

    fig, ax = plt.subplots(figsize=(7, 6))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    color_cycle = plt.rcParams.get("axes.prop_cycle", None)
    default_colors = (color_cycle.by_key().get("color", []) if color_cycle else []) or [
        "tab:blue",
        "tab:orange",
        "tab:green",
        "tab:red",
        "tab:purple",
        "tab:brown",
    ]
    comp_names = sorted(by_comp_points.keys())
    comp_colors = {c: default_colors[i % len(default_colors)] for i, c in enumerate(comp_names)}

    for comp in comp_names:
        pts = by_comp_points[comp]
        if not pts:
            continue
        arr = np.asarray(pts, dtype=np.float64)
        xx = arr[:, 0]
        yy = arr[:, 1]
        color = comp_colors[comp]

        ax.scatter(xx, yy, color=color, alpha=0.55, s=24, label=comp)

    ax.set_xscale("log")
    ax.set_yscale("log")
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


def scatter_xy_by_compressor(plot_dir, rows, x_col, y_col, xlabel, ylabel, title, filename):
    by_comp_points = {}
    for r in rows:
        comp = r.get("compressor name", "").strip() or "default"
        x = to_float(r.get(x_col))
        y = to_float(r.get(y_col))
        if np.isnan(x) or np.isnan(y):
            continue
        if y <= 0:
            y = Y_EPSILON
        if comp not in by_comp_points:
            by_comp_points[comp] = []
        by_comp_points[comp].append((x, y))

    fig, ax = plt.subplots(figsize=(7, 6))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    color_cycle = plt.rcParams.get("axes.prop_cycle", None)
    default_colors = (color_cycle.by_key().get("color", []) if color_cycle else []) or [
        "tab:blue",
        "tab:orange",
        "tab:green",
        "tab:red",
        "tab:purple",
        "tab:brown",
    ]
    comp_names = sorted(by_comp_points.keys())
    comp_colors = {c: default_colors[i % len(default_colors)] for i, c in enumerate(comp_names)}

    for comp in comp_names:
        pts = by_comp_points[comp]
        if not pts:
            continue
        arr = np.asarray(pts, dtype=np.float64)
        xx = arr[:, 0]
        yy = arr[:, 1]
        ax.scatter(xx, yy, color=comp_colors[comp], alpha=0.7, s=24, label=comp)

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

    datasets = list_datasets()
    if not datasets:
        print(
            "No datasets found (need STANDARD/NYX/<name>/<compressor>_standard.csv "
            "and HALO/NYX/<name>/<compressor>_halo.csv)"
        )
        raise SystemExit(1)

    print("Datasets (aggregated):", datasets)
    raw = gather_all_merged_rows()
    if not raw:
        print("No merged rows; abort.")
        raise SystemExit(1)

    filtered = filter_by_error_bounds(raw)
    print(f"Rows before EB filter: {len(raw)}, after ({len(ERROR_BOUNDS)} bounds): {len(filtered)}")

    add_bit_rate(filtered)
    rows = aggregate_mean_by_compressor_and_eb(filtered)

    print(
        f"Aggregated points: {len(rows)} (compressors: "
        f"{sorted(set(r.get('compressor name', '').strip() for r in rows))})"
    )

    prefix = "nyx_mean_"
    title_suffix = " (NYX mean over datasets)"

    qoi_vs_bit_rate(
        PLOT_OUT,
        rows,
        "wasserstein_distance",
        "Wasserstein distance",
        "Wasserstein vs Bit rate" + title_suffix,
        prefix + "wasserstein_vs_bit_rate.png",
    )
    qoi_vs_bit_rate(
        PLOT_OUT,
        rows,
        "p99",
        "p99 Nearest-Neighbor Distance",
        "p99 Nearest-Neighbor Distance Error vs Bit rate" + title_suffix,
        prefix + "p99_vs_bit_rate.png",
    )
    qoi_vs_bit_rate(
        PLOT_OUT,
        rows,
        "p90",
        "p90 Nearest-Neighbor Distance",
        "p90 Nearest-Neighbor Distance Error vs Bit rate" + title_suffix,
        prefix + "p90_vs_bit_rate.png",
    )
    scatter_xy_by_compressor(
        PLOT_OUT,
        rows,
        "psnr",
        "wasserstein_distance",
        "PSNR (dB)",
        "Wasserstein distance",
        "Wasserstein vs PSNR" + title_suffix,
        prefix + "wasserstein_vs_psnr.png",
    )
    scatter_xy_by_compressor(
        PLOT_OUT,
        rows,
        "ssim",
        "wasserstein_distance",
        "SSIM",
        "Wasserstein distance",
        "Wasserstein vs SSIM" + title_suffix,
        prefix + "wasserstein_vs_ssim.png",
    )
    scatter_xy_by_compressor(
        PLOT_OUT,
        rows,
        "psnr",
        "p90",
        "PSNR (dB)",
        "p90 Nearest-Neighbor Distance",
        "p90 Nearest-Neighbor Distance vs PSNR" + title_suffix,
        prefix + "p90_vs_psnr.png",
    )
    scatter_xy_by_compressor(
        PLOT_OUT,
        rows,
        "ssim",
        "p90",
        "SSIM",
        "p90 Nearest-Neighbor Distance",
        "p90 Nearest-Neighbor Distance vs SSIM" + title_suffix,
        prefix + "p90_vs_ssim.png",
    )

    print("\nAll plots saved under", PLOT_OUT)


if __name__ == "__main__":
    main()
