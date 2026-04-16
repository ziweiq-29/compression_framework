#!/usr/bin/env python3
"""
Build a single tabular CSV from app_eval_compress_many_summary_*.csv files.

Input CSV columns used:
  - compressor
  - error_bound
  - mean_app_eval_sec
  - mean_compress_many

Ignored on purpose:
  - count_paired / count_app_eval / mean_app_eval_sec_paired

Output:
  - one CSV (default: .../outputs/apps_time/app_eval_time_table.csv)
  - numeric columns formatted to two decimal places
"""

import argparse
import csv
import math
import os
from typing import Dict, List, Tuple


DEFAULT_FILES = [
    "/anvil/projects/x-cis240669/compression_framework/outputs/app_eval_compress_many_summary_cesm.csv",
    "/anvil/projects/x-cis240669/compression_framework/outputs/app_eval_compress_many_summary_fidelity.csv",
    "/anvil/projects/x-cis240669/compression_framework/outputs/app_eval_compress_many_summary_halo.csv",
    "/anvil/projects/x-cis240669/compression_framework/outputs/app_eval_compress_many_summary_hedm.csv",
    "/anvil/projects/x-cis240669/compression_framework/outputs/app_eval_compress_many_summary_rdf.csv",
]

COMP_ORDER = ["mgard", "sperr", "sz3", "zfp"]
EB_ORDER = ["1e-2", "1e-3", "1e-4"]

DEFAULT_OUT_DIR = (
    "/anvil/projects/x-cis240669/compression_framework/outputs/apps_time"
)

DEFAULT_CSV_NAME = "app_eval_time_table.csv"


def app_name_from_path(path: str) -> str:
    base = os.path.basename(path).lower()
    if "cesm" in base:
        return "CESM"
    if "fidelity" in base:
        return "Quantum"
    if "halo" in base:
        return "HALO"
    if "hedm" in base:
        return "FF-HEDM"
    if "rdf" in base:
        return "RDF"
    return os.path.splitext(os.path.basename(path))[0]


def parse_float(x: str) -> float:
    try:
        return float(x)
    except Exception:
        return float("nan")


def load_rows(path: str) -> List[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows


def ordered_items(seen: List[str], preferred: List[str]) -> List[str]:
    out = [x for x in preferred if x in seen]
    out.extend([x for x in seen if x not in out])
    return out


def collect_axes_domains(app_rows: Dict[str, List[dict]]) -> Tuple[List[str], List[str]]:
    seen_comp = []
    seen_eb = []
    for rows in app_rows.values():
        for r in rows:
            c = str(r.get("compressor", "")).strip().lower()
            e = str(r.get("error_bound", "")).strip()
            if c and c not in seen_comp:
                seen_comp.append(c)
            if e and e not in seen_eb:
                seen_eb.append(e)
    comp_order = ordered_items(seen_comp, COMP_ORDER)
    eb_order = ordered_items(seen_eb, EB_ORDER)
    return comp_order, eb_order


def rows_to_lookup(rows: List[dict]) -> Dict[Tuple[str, str], Tuple[float, float]]:
    """
    Return map:
      (compressor, error_bound) -> (compress_time, qoi_eval_time)
    """
    d = {}
    for r in rows:
        comp = str(r.get("compressor", "")).strip().lower()
        eb = str(r.get("error_bound", "")).strip()
        qoi = parse_float(str(r.get("mean_app_eval_sec", "")))
        comp_t = parse_float(str(r.get("mean_compress_many", "")))
        if not comp or not eb or math.isnan(qoi) or math.isnan(comp_t):
            continue
        d[(comp, eb)] = (comp_t, qoi)
    return d


def _fmt2(x: float) -> str:
    if not math.isfinite(x):
        return ""
    return f"{x:.2f}"


def write_app_time_table(app_rows: Dict[str, List[dict]], out_path: str) -> str:
    """Long-format table: one row per (application, compressor, error_bound)."""
    comp_order, eb_order = collect_axes_domains(app_rows)
    apps = ["HALO", "FF-HEDM", "CESM", "Quantum", "RDF"]
    apps = [a for a in apps if a in app_rows] + [a for a in app_rows if a not in apps]

    fieldnames = [
        "application",
        "compressor",
        "error_bound",
        "qoi_compress_sec",
        "app_eval_sec",
        "total_sec",
    ]
    parent = os.path.dirname(os.path.abspath(out_path))
    if parent:
        os.makedirs(parent, exist_ok=True)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for app in apps:
            lookup = rows_to_lookup(app_rows[app])
            for comp in comp_order:
                for eb in eb_order:
                    row = {
                        "application": app,
                        "compressor": comp,
                        "error_bound": eb,
                        "qoi_compress_sec": "",
                        "app_eval_sec": "",
                        "total_sec": "",
                    }
                    t = lookup.get((comp, eb))
                    if t is not None:
                        comp_t, qoi_t = t
                        if math.isfinite(comp_t) and math.isfinite(qoi_t):
                            row["qoi_compress_sec"] = _fmt2(comp_t)
                            row["app_eval_sec"] = _fmt2(qoi_t)
                            row["total_sec"] = _fmt2(comp_t + qoi_t)
                    w.writerow(row)
    return out_path


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--csvs",
        nargs="+",
        default=DEFAULT_FILES,
        help="summary csv paths",
    )
    p.add_argument(
        "--out-dir",
        default=DEFAULT_OUT_DIR,
        help="directory for output CSV when --out-csv is not set",
    )
    p.add_argument(
        "--out-csv",
        default=None,
        help=f"output table path (default: <out-dir>/{DEFAULT_CSV_NAME})",
    )
    return p.parse_args()


def main():
    args = parse_args()

    app_rows: Dict[str, List[dict]] = {}
    for f in args.csvs:
        if not os.path.isfile(f):
            raise SystemExit(f"Missing file: {f}")
        app = app_name_from_path(f)
        app_rows[app] = load_rows(f)

    out_path = args.out_csv
    if not out_path:
        os.makedirs(args.out_dir, exist_ok=True)
        out_path = os.path.join(args.out_dir, DEFAULT_CSV_NAME)

    print("Saved:", write_app_time_table(app_rows, out_path))


if __name__ == "__main__":
    main()
