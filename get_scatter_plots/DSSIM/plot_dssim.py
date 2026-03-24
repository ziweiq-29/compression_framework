"""
Plot QoI vs bit rate for DSSIM results, aggregated over all variable folders.

Walks outputs/DSSIM/<dataset>/<group>/<leaf>/ <compressor>_dssim.csv, pairs each with
outputs/STANDARD/<dataset>/<standard_leaf>/<compressor>_standard.csv where
standard_leaf = <dssim_leaf> with the first "<group>_" prefix stripped
(e.g. FLDSC/FLDSC_FLDSC_00_dat -> FLDSC_00_dat).

Keeps error_bound in the same list as run_all_compressors.py (lines 21–33),
then for each (compressor × error_bound) takes the arithmetic mean of every
numeric column across all merged rows.

Outputs under get_scatter_plots/DSSIM/outputs/ (csv + numpy + matplotlib only).
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
DSSIM_ROOT = os.path.join(BASE_DIR, "DSSIM")
STANDARD_ROOT = os.path.join(BASE_DIR, "STANDARD")
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


_EB_NORM_TO_CANON = {_norm_eb(eb): eb for eb in ERROR_BOUNDS}
_ALLOWED_EB_NORM = set(_EB_NORM_TO_CANON.keys())


def standard_leaf_from_dssim(group: str, dssim_leaf: str) -> str:
    """Map DSSIM folder leaf to STANDARD/CESM/<leaf> style folder name."""
    prefix = f"{group}_"
    if dssim_leaf.startswith(prefix):
        return dssim_leaf[len(prefix) :]
    return dssim_leaf


def read_csv(path):
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def merge_rows(std_rows, dssim_rows):
    dssim_by_key = {}
    for r in dssim_rows:
        k = (r.get("compressor name", "").strip(), r.get("error_bound", "").strip())
        dssim_by_key[k] = r
    merged = []
    for r in std_rows:
        k = (r.get("compressor name", "").strip(), r.get("error_bound", "").strip())
        if k in dssim_by_key:
            out = dict(r)
            out.update(dssim_by_key[k])
            merged.append(out)
    return merged


def to_float(x, default=np.nan):
    if x is None or (isinstance(x, str) and x.strip() in ("", "<empty>")):
        return default
    try:
        return float(x)
    except (ValueError, TypeError):
        return default


def iter_dssim_standard_pairs():
    """
    Yield (dataset, group, dssim_leaf, std_leaf, compressor, dssim_csv, standard_csv).
    """
    if not os.path.isdir(DSSIM_ROOT):
        return
    for dataset in sorted(os.listdir(DSSIM_ROOT)):
        ds_path = os.path.join(DSSIM_ROOT, dataset)
        if not os.path.isdir(ds_path):
            continue
        for group in sorted(os.listdir(ds_path)):
            g_path = os.path.join(ds_path, group)
            if not os.path.isdir(g_path):
                continue
            for leaf in sorted(os.listdir(g_path)):
                dssim_dir = os.path.join(g_path, leaf)
                if not os.path.isdir(dssim_dir):
                    continue
                std_leaf = standard_leaf_from_dssim(group, leaf)
                std_dir = os.path.join(STANDARD_ROOT, dataset, std_leaf)
                if not os.path.isdir(std_dir):
                    continue
                for comp in COMPRESSORS:
                    dc = os.path.join(dssim_dir, f"{comp}_dssim.csv")
                    sc = os.path.join(std_dir, f"{comp}_standard.csv")
                    if os.path.isfile(dc) and os.path.isfile(sc):
                        yield dataset, group, leaf, std_leaf, comp, dc, sc


def gather_all_merged_rows():
    rows = []
    for _ds, _g, _lf, _sl, comp, dcsv, scsv in iter_dssim_standard_pairs():
        std_rows = read_csv(scsv)
        dss_rows = read_csv(dcsv)
        rows.extend(merge_rows(std_rows, dss_rows))
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

    mean_rows.sort(
        key=lambda r: (r.get("compressor name", ""), to_float(r.get("error_bound"), 0.0))
    )
    return mean_rows


def qoi_vs_bit_rate(
    plot_dir,
    rows,
    y_col,
    ylabel,
    filename,
    *,
    log_y=True,
    xlim=None,
    ylim=None,
    one_minus_y=False,
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
    if log_y:
        ax.set_yscale("log")
    if xlim is not None:
        ax.set_xlim(*xlim)
    if ylim is not None:
        ax.set_ylim(*ylim)
    ax.set_xlabel("Bit rate", fontsize=12, color="black")
    ax.set_ylabel(("1 - " + ylabel) if one_minus_y else ylabel, fontsize=12, color="black")
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


def scatter_xy_by_compressor(
    plot_dir,
    rows,
    x_col,
    y_col,
    xlabel,
    ylabel,
    filename,
    *,
    log_y=True,
):
    by_comp_points = {}
    for r in rows:
        comp = r.get("compressor name", "").strip() or "default"
        x = to_float(r.get(x_col))
        y = to_float(r.get(y_col))
        if np.isnan(x) or np.isnan(y):
            continue
        if log_y and y <= 0:
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
    if log_y:
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

    if not os.path.isdir(DSSIM_ROOT):
        print(f"No DSSIM outputs at {DSSIM_ROOT}")
        raise SystemExit(1)

    raw = gather_all_merged_rows()
    if not raw:
        print(
            "No merged rows. Need outputs/DSSIM/<dataset>/<group>/<leaf>/<comp>_dssim.csv "
            "paired with outputs/STANDARD/<dataset>/<mapped_leaf>/<comp>_standard.csv"
        )
        raise SystemExit(1)

    filtered = filter_by_error_bounds(raw)
    print(
        f"Merged DSSIM+STANDARD rows: {len(raw)}, after error_bound filter ({len(ERROR_BOUNDS)}): {len(filtered)}"
    )

    add_bit_rate(filtered)
    rows = aggregate_mean_by_compressor_and_eb(filtered)

    print(
        f"Aggregated points: {len(rows)} (compressors: "
        f"{sorted(set(r.get('compressor name', '').strip() for r in rows))})"
    )

    prefix = "dssim_mean_"

    # DSSIM scalar: linear y (values near 1)
    qoi_vs_bit_rate(
        PLOT_OUT,
        rows,
        "dssim",
        "DSSIM",
        prefix + "dssim_vs_bit_rate.png",
        log_y=True,
        one_minus_y=True,
    )
    qoi_vs_bit_rate(
        PLOT_OUT,
        rows,
        "wasserstein_distance",
        "Wasserstein distance",
        prefix + "wasserstein_vs_bit_rate.png",
    )
    qoi_vs_bit_rate(
        PLOT_OUT,
        rows,
        "p99",
        "p99 Nearest-Neighbor Distance",
        prefix + "p99_vs_bit_rate.png",
    )
    qoi_vs_bit_rate(
        PLOT_OUT,
        rows,
        "p90",
        "p90 Nearest-Neighbor Distance",
        prefix + "p90_vs_bit_rate.png",
    )
    scatter_xy_by_compressor(
        PLOT_OUT,
        rows,
        "psnr",
        "wasserstein_distance",
        "PSNR (dB)",
        "Wasserstein distance",
        prefix + "wasserstein_vs_psnr.png",
    )
    scatter_xy_by_compressor(
        PLOT_OUT,
        rows,
        "ssim",
        "wasserstein_distance",
        "SSIM",
        "Wasserstein distance",
        prefix + "wasserstein_vs_ssim.png",
    )
    scatter_xy_by_compressor(
        PLOT_OUT,
        rows,
        "psnr",
        "p90",
        "PSNR (dB)",
        "p90 Nearest-Neighbor Distance",
        prefix + "p90_vs_psnr.png",
    )
    scatter_xy_by_compressor(
        PLOT_OUT,
        rows,
        "ssim",
        "p90",
        "SSIM",
        "p90 Nearest-Neighbor Distance",
        prefix + "p90_vs_ssim.png",
    )
    scatter_xy_by_compressor(
        PLOT_OUT,
        rows,
        "psnr",
        "dssim",
        "PSNR (dB)",
        "DSSIM",
        prefix + "dssim_vs_psnr.png",
        log_y=False,
    )
    scatter_xy_by_compressor(
        PLOT_OUT,
        rows,
        "ssim",
        "dssim",
        "SSIM",
        "DSSIM",
        prefix + "dssim_vs_ssim.png",
        log_y=False,
    )

    print("\nAll plots saved under", PLOT_OUT)


if __name__ == "__main__":
    main()
