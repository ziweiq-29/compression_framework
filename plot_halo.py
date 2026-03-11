"""
Plot halo metrics (Wasserstein, p99, p90) vs SSIM, PSNR, bit rate.
Uses only csv + numpy + matplotlib to avoid pandas/numpy ABI issues on HPC.
"""
import sys
import os

# Ensure venv packages are used first (avoid system numpy 1.19.5 when loading matplotlib)
if sys.prefix != sys.base_prefix:
    _venv_site = os.path.join(
        sys.prefix, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages"
    )
    if os.path.isdir(_venv_site):
        sys.path.insert(0, _venv_site)
        _prefix_abs = os.path.abspath(sys.prefix)
        sys.path = [p for p in sys.path if "site-packages" not in p or _prefix_abs in os.path.abspath(p)]

import csv
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ================= paths =================
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.join(_SCRIPT_DIR, "outputs")
STANDARD_NYX = os.path.join(BASE_DIR, "STANDARD", "NYX")
HALO_NYX = os.path.join(BASE_DIR, "HALO", "NYX")
PLOT_BASE = os.path.join(BASE_DIR, "HALO", "NYX", "plots")


# Compressors to include in the same plot (each needs <name>_standard.csv and <name>_halo.csv)
COMPRESSORS = ["sz3", "zfp","sperr","mgard"]


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


def scatter_one(plot_dir, rows, x_col, y_col, xlabel, ylabel, title, filename, skip_nan=True):
    by_comp = {}
    for r in rows:
        comp = r.get("compressor name", "").strip() or "default"
        x = to_float(r.get(x_col))
        y = to_float(r.get(y_col))
        if skip_nan and (np.isnan(y) or np.isnan(x)):
            continue
        if comp not in by_comp:
            by_comp[comp] = ([], [])
        by_comp[comp][0].append(x)
        by_comp[comp][1].append(y)
    fig, ax = plt.subplots(figsize=(7, 6))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    for comp, (xx, yy) in by_comp.items():
        if xx and yy:
            ax.scatter(np.asarray(xx, dtype=np.float64), np.asarray(yy, dtype=np.float64), label=comp, alpha=0.7)
    ax.set_xlabel(xlabel, fontsize=12, color="black")
    ax.set_ylabel(ylabel, fontsize=12, color="black")
    ax.set_title(title, fontsize=14, color="black")
    ax.tick_params(axis="both", labelsize=10, colors="black")
    for spine in ax.spines.values():
        spine.set_color("black")
    leg = ax.legend(fontsize=10)
    leg.get_frame().set_facecolor("white")
    for t in leg.get_texts():
        t.set_color("black")
    ax.grid(True, color="gray", alpha=0.5)
    fig.tight_layout(pad=1.2)
    out = os.path.join(plot_dir, filename)
    fig.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print(f"Saved {out}")


os.makedirs(PLOT_BASE, exist_ok=True)
datasets = list_datasets()
if not datasets:
    print("No datasets found (need STANDARD/NYX/<name>/<compressor>_standard.csv and HALO/NYX/<name>/<compressor>_halo.csv)")
    raise SystemExit(1)
print("Datasets:", datasets)

for dataset_var in datasets:
    plot_dir = os.path.join(PLOT_BASE, dataset_var)
    os.makedirs(plot_dir, exist_ok=True)
    print(f"\n=== {dataset_var} ===")

    rows = []
    for comp in COMPRESSORS:
        results_csv = os.path.join(STANDARD_NYX, dataset_var, comp + "_standard.csv")
        halo_csv = os.path.join(HALO_NYX, dataset_var, comp + "_halo.csv")
        if not os.path.isfile(results_csv) or not os.path.isfile(halo_csv):
            continue
        std_rows = read_csv(results_csv)
        halo_rows = read_csv(halo_csv)
        rows.extend(merge_rows(std_rows, halo_rows))
    if not rows:
        print(f"  No data for any compressor, skip.")
        continue
    for r in rows:
        cr = to_float(r.get("compression_ratio"), default=0.0)
        r["bit_rate"] = (32.0 / cr) if cr and cr > 0 else np.nan
    rows.sort(key=lambda r: to_float(r.get("error_bound"), default=0.0))
    print(f"Merged rows: {len(rows)} (compressors: {sorted(set(r.get('compressor name','').strip() for r in rows))})")

    scatter_one(plot_dir, rows, "ssim", "wasserstein_distance",
                "SSIM", "Wasserstein distance", "Wasserstein vs SSIM", "wasserstein_vs_ssim.png")
    scatter_one(plot_dir, rows, "psnr", "wasserstein_distance",
                "PSNR (dB)", "Wasserstein distance", "Wasserstein vs PSNR", "wasserstein_vs_psnr.png")
    scatter_one(plot_dir, rows, "ssim", "p99",
                "SSIM", "p99 error", "p99 error vs SSIM", "p99_vs_ssim.png")
    scatter_one(plot_dir, rows, "psnr", "p90",
                "PSNR (dB)", "p90 error", "p90 error vs PSNR", "p90_vs_psnr.png")
    rows_bit = [r for r in rows if not np.isnan(to_float(r.get("bit_rate")))]
    rows_bit.sort(key=lambda r: to_float(r.get("error_bound"), default=0.0))
    scatter_one(plot_dir, rows_bit, "bit_rate", "wasserstein_distance",
                "Bit rate (bits/value)", "Wasserstein distance", "Wasserstein vs bit rate",
                "wasserstein_vs_bit_rate.png")
    scatter_one(plot_dir, rows_bit, "bit_rate", "p99",
                "Bit rate (bits/value)", "p99 error", "p99 error vs bit rate", "p99_vs_bit_rate.png")

print("\nAll plots saved under", PLOT_BASE)
