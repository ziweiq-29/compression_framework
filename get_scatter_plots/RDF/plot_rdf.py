"""
Plot QoI vs bit rate for RDF, using only SDRBENCH-exaalt-copper.

Key rule (as requested): do NOT treat x/y/z as 3 points.
For each (compressor, dataset, error_bound), first merge x/y/z into ONE bit-rate
point, then merge with RDF metrics row and plot.

Inputs:
- RDF metrics: outputs/RDF/SDRBENCH-exaalt-copper/<dataset>_f32/<comp>_rdf.csv
- STANDARD axis stats: outputs/STANDARD/EXAALT/SDRBENCH-exaalt-copper_<dataset>_{x|y|z}_f32_dat/<comp>_standard.csv

Outputs:
- get_scatter_plots/RDF/outputs/
"""
import sys
import os
import site
import re
import csv
from collections import defaultdict

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

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BASE_CF = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))
BASE_DIR = os.path.join(_BASE_CF, "outputs")
RDF_ROOT = os.path.join(BASE_DIR, "RDF", "SDRBENCH-exaalt-copper")
STD_ROOT = os.path.join(BASE_DIR, "STANDARD", "EXAALT")
PLOT_OUT = os.path.join(_SCRIPT_DIR, "outputs")

ERROR_BOUNDS = [
    "1e-6", "5e-6", "1e-5", "5e-5", "1e-4", "5e-4", "1e-3", "5e-3", "1e-2", "5e-2", "1e-1"
]
COMPRESSORS = ["sz3", "zfp", "sperr", "mgard"]
Y_EPSILON = 1e-12
SKIP_MEAN_KEYS = {"compressor name", "input", "error_bound", "dataset"}
STD_DIR_RE = re.compile(r"^SDRBENCH-exaalt-copper_(dataset\d+-\d+x\d+)_([xyz])_f32_dat$")
RDF_DATASET_RE = re.compile(r"^(dataset\d+-\d+x\d+)_f32$")


def _compressor_color_map_fixed():
    """
    Fixed compressor->color mapping to match HEDM/plot_hedm.py.

    COMPRESSORS = ["sz3", "zfp", "sperr", "mgard"]
    tab palette order is:
      sz3   -> tab:blue
      zfp   -> tab:orange
      sperr -> tab:green
      mgard -> tab:red
    """
    fixed_colors = ["tab:blue", "tab:orange", "tab:green", "tab:red"]
    return {c: fixed_colors[i % len(fixed_colors)] for i, c in enumerate(COMPRESSORS)}


def _norm_eb(s: str) -> str:
    t = (s or "").strip()
    if not t:
        return ""
    try:
        return f"{float(t):.12g}"
    except (ValueError, TypeError):
        return t


def to_float(x, default=np.nan):
    if x is None or (isinstance(x, str) and x.strip() in ("", "<empty>")):
        return default
    try:
        return float(x)
    except (ValueError, TypeError):
        return default


_EB_NORM_TO_CANON = {_norm_eb(eb): eb for eb in ERROR_BOUNDS}
_ALLOWED_EB_NORM = set(_EB_NORM_TO_CANON.keys())


def read_csv(path):
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def gather_standard_xyz_aggregates():
    """
    Build one STANDARD aggregate row per (compressor, dataset, error_bound),
    where bit-rate is computed from summed x/y/z sizes.
    """
    by_key = defaultdict(list)  # key -> list[axis_row]

    if not os.path.isdir(STD_ROOT):
        return []

    for dname in sorted(os.listdir(STD_ROOT)):
        m = STD_DIR_RE.match(dname)
        if not m:
            continue
        dataset, axis = m.group(1), m.group(2)
        dpath = os.path.join(STD_ROOT, dname)
        if not os.path.isdir(dpath):
            continue
        for comp in COMPRESSORS:
            csv_path = os.path.join(dpath, f"{comp}_standard.csv")
            if not os.path.isfile(csv_path):
                continue
            for row in read_csv(csv_path):
                eb_n = _norm_eb(row.get("error_bound", ""))
                if eb_n not in _ALLOWED_EB_NORM:
                    continue
                key = (comp, dataset, eb_n)
                r = dict(row)
                r["_axis"] = axis
                by_key[key].append(r)

    out_rows = []
    for (comp, dataset, eb_n), rows in by_key.items():
        # Require all 3 axes to form one point
        axes = {r.get("_axis") for r in rows}
        if axes != {"x", "y", "z"}:
            continue

        all_keys = set()
        for r in rows:
            all_keys.update(r.keys())

        out = {
            "compressor name": comp,
            "dataset": dataset,
            "error_bound": _EB_NORM_TO_CANON.get(eb_n, eb_n),
        }

        # Aggregate numeric metrics across axes by arithmetic mean (except bit-rate handled below)
        for k in sorted(all_keys):
            if k in ("_axis", "compressor name", "input", "error_bound"):
                continue
            vals = [to_float(r.get(k)) for r in rows]
            vals = [v for v in vals if np.isfinite(v)]
            if vals:
                out[k] = float(np.mean(vals))

        # One-point bit-rate from summed sizes across xyz (preferred)
        comp_sizes = [to_float(r.get("compressed_size")) for r in rows]
        uncomp_sizes = [to_float(r.get("uncompressed_size")) for r in rows]
        if all(np.isfinite(v) and v > 0 for v in comp_sizes + uncomp_sizes):
            total_comp = float(np.sum(comp_sizes))
            total_uncomp = float(np.sum(uncomp_sizes))
            cr_total = total_uncomp / total_comp
            out["compression_ratio"] = cr_total
            out["bit_rate"] = 32.0 / cr_total
        else:
            # fallback: average axis bit_rate
            brs = [to_float(r.get("bit_rate")) for r in rows]
            brs = [v for v in brs if np.isfinite(v) and v > 0]
            out["bit_rate"] = float(np.mean(brs)) if brs else np.nan

        out_rows.append(out)

    return out_rows


def gather_rdf_rows():
    rows = []
    if not os.path.isdir(RDF_ROOT):
        return rows
    for dname in sorted(os.listdir(RDF_ROOT)):
        m = RDF_DATASET_RE.match(dname)
        if not m:
            continue
        dataset = m.group(1)
        dpath = os.path.join(RDF_ROOT, dname)
        if not os.path.isdir(dpath):
            continue
        for comp in COMPRESSORS:
            csv_path = os.path.join(dpath, f"{comp}_rdf.csv")
            if not os.path.isfile(csv_path):
                continue
            for row in read_csv(csv_path):
                eb_n = _norm_eb(row.get("error_bound", ""))
                if eb_n not in _ALLOWED_EB_NORM:
                    continue
                r = dict(row)
                r["dataset"] = dataset
                r["error_bound"] = _EB_NORM_TO_CANON.get(eb_n, eb_n)
                rows.append(r)
    return rows


def merge_standard_with_rdf(std_rows, rdf_rows):
    rdf_by_key = {}
    for r in rdf_rows:
        key = (
            r.get("compressor name", "").strip(),
            r.get("dataset", "").strip(),
            _norm_eb(r.get("error_bound", "")),
        )
        rdf_by_key[key] = r

    merged = []
    for s in std_rows:
        key = (
            s.get("compressor name", "").strip(),
            s.get("dataset", "").strip(),
            _norm_eb(s.get("error_bound", "")),
        )
        if key in rdf_by_key:
            out = dict(s)
            out.update(rdf_by_key[key])
            merged.append(out)
    return merged


def aggregate_mean_by_compressor_and_eb(rows):
    groups = defaultdict(list)
    for r in rows:
        comp = r.get("compressor name", "").strip() or "default"
        eb_n = _norm_eb(r.get("error_bound", ""))
        if eb_n in _ALLOWED_EB_NORM:
            groups[(comp, eb_n)].append(r)

    all_keys = set()
    for r in rows:
        all_keys.update(r.keys())

    out_rows = []
    for (comp, eb_n), grp in sorted(groups.items(), key=lambda x: (x[0][0], float(x[0][1] or 0))):
        out = {"compressor name": comp, "error_bound": _EB_NORM_TO_CANON.get(eb_n, eb_n)}
        for k in sorted(all_keys):
            if k in SKIP_MEAN_KEYS:
                continue
            vals = [to_float(r.get(k)) for r in grp]
            vals = [v for v in vals if np.isfinite(v)]
            if vals:
                out[k] = float(np.mean(vals))
        out_rows.append(out)
    return out_rows


def qoi_vs_bit_rate(
    plot_dir,
    rows,
    y_col,
    ylabel,
    filename,
    *,
    y_bottom=None,
    plot_kind="scatter",
):
    by_comp = defaultdict(list)
    for r in rows:
        comp = r.get("compressor name", "").strip() or "default"
        x = to_float(r.get("bit_rate"))
        y = to_float(r.get(y_col))
        if np.isnan(x) or np.isnan(y):
            continue
        if y <= 0:
            y = Y_EPSILON
        by_comp[comp].append((x, y))

    fig, ax = plt.subplots(figsize=(7, 6))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    comp_colors = _compressor_color_map_fixed()
    linestyle_cycle = ["-", "--", "-.", ":"]
    marker_cycle = ["o", "^", "s", "D", "v", "P", "X", "*"]
    comp_linestyles = {c: linestyle_cycle[i % len(linestyle_cycle)] for i, c in enumerate(COMPRESSORS)}
    comp_markers = {c: marker_cycle[i % len(marker_cycle)] for i, c in enumerate(COMPRESSORS)}

    ordered_comps = [c for c in COMPRESSORS if c in by_comp] + sorted([c for c in by_comp.keys() if c not in COMPRESSORS])
    for comp in ordered_comps:
        arr = np.asarray(by_comp[comp], dtype=np.float64)
        if arr.size == 0:
            continue

        xx = arr[:, 0]
        yy = arr[:, 1]
        color = comp_colors.get(comp, "gray")
        if plot_kind == "scatter":
            ax.scatter(xx, yy, color=color, alpha=0.55, s=24, label=comp.upper())
        elif plot_kind == "line":
            # log-x plot, so filter non-positive x values.
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
    ax.set_yscale("log")
    if y_bottom is not None:
        ax.set_ylim(bottom=float(y_bottom))
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
    ax.grid(True, axis="both", which="major", linestyle="--", alpha=0.35)
    fig.tight_layout(pad=1.2)
    out = os.path.join(plot_dir, filename)
    fig.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print(f"Saved {out}")


def scatter_xy_by_compressor(plot_dir, rows, x_col, y_col, xlabel, ylabel, filename):
    by_comp = defaultdict(list)
    for r in rows:
        comp = r.get("compressor name", "").strip() or "default"
        x = to_float(r.get(x_col))
        y = to_float(r.get(y_col))
        if np.isnan(x) or np.isnan(y):
            continue
        if y <= 0:
            y = Y_EPSILON
        by_comp[comp].append((x, y))

    fig, ax = plt.subplots(figsize=(7, 6))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    comp_colors = _compressor_color_map_fixed()
    ordered_comps = [c for c in COMPRESSORS if c in by_comp] + sorted([c for c in by_comp.keys() if c not in COMPRESSORS])
    for comp in ordered_comps:
        arr = np.asarray(by_comp[comp], dtype=np.float64)
        if arr.size == 0:
            continue
        ax.scatter(arr[:, 0], arr[:, 1], color=comp_colors.get(comp, "gray"), alpha=0.7, s=24, label=comp.upper())

    ax.set_xlabel(xlabel, fontsize=25, color="black")
    ax.set_ylabel(ylabel, fontsize=25, color="black")
    ax.set_yscale("log")
    ax.tick_params(axis="both", labelsize=18, colors="black")
    for spine in ax.spines.values():
        spine.set_color("black")
    leg = ax.legend(fontsize=25)
    leg.get_frame().set_facecolor("white")
    for t in leg.get_texts():
        t.set_color("black")
    ax.set_axisbelow(True)
    ax.grid(True, axis="both", which="major", linestyle="--", alpha=0.35)
    fig.tight_layout(pad=1.2)
    out = os.path.join(plot_dir, filename)
    fig.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print(f"Saved {out}")


def main():
    os.makedirs(PLOT_OUT, exist_ok=True)

    std_xyz = gather_standard_xyz_aggregates()
    rdf_rows = gather_rdf_rows()
    if not std_xyz or not rdf_rows:
        print("Missing RDF/STANDARD inputs for SDRBENCH-exaalt-copper")
        raise SystemExit(1)

    merged = merge_standard_with_rdf(std_xyz, rdf_rows)
    if not merged:
        print("No merged rows after key matching (compressor, dataset, error_bound)")
        raise SystemExit(1)

    rows = aggregate_mean_by_compressor_and_eb(merged)

    print(f"std_xyz rows: {len(std_xyz)} | rdf rows: {len(rdf_rows)} | merged: {len(merged)} | aggregated: {len(rows)}")

    prefix = "rdf_copper_mean_"
    qoi_vs_bit_rate(
        PLOT_OUT,
        rows,
        "wasserstein_distance",
        "Wasserstein distance",
        prefix + "wasserstein_vs_bit_rate.png",
        y_bottom=1e-6,
        plot_kind="line",
    )
    qoi_vs_bit_rate(PLOT_OUT, rows, "p99", "p99", prefix + "p99_vs_bit_rate.png")
    qoi_vs_bit_rate(PLOT_OUT, rows, "p90", "p90", prefix + "p90_vs_bit_rate.png")
    scatter_xy_by_compressor(PLOT_OUT, rows, "psnr", "wasserstein_distance", "PSNR (dB)", "Wasserstein distance", prefix + "wasserstein_vs_psnr.png")
    scatter_xy_by_compressor(PLOT_OUT, rows, "ssim", "wasserstein_distance", "SSIM", "Wasserstein distance", prefix + "wasserstein_vs_ssim.png")
    scatter_xy_by_compressor(PLOT_OUT, rows, "psnr", "p90", "PSNR (dB)", "p90", prefix + "p90_vs_psnr.png")
    scatter_xy_by_compressor(PLOT_OUT, rows, "ssim", "p90", "SSIM", "p90", prefix + "p90_vs_ssim.png")

    print("\nAll plots saved under", PLOT_OUT)


if __name__ == "__main__":
    main()
