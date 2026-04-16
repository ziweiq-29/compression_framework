#!/usr/bin/env python3
"""Run pressio + DSSIM external metric and write results to CSV (same logic as run_hedm.py)."""
import argparse
import csv
import os
import re
import subprocess
import sys
import time

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PRESSIO = "/anvil/projects/x-cis240669/libpressio-env/.spack-env/view/bin/pressio"
DSSIM_EXTERNAL = "/anvil/projects/x-cis240669/DSSIM/run_dssim_pipeline.py"
DSSIM_PYTHON = "/anvil/projects/x-cis240669/DSSIM/dssim-env/bin/python"

QOI_KEYS = ["mean", "min", "max", "median", "p90", "p99", "p999", "wasserstein_distance"]
DSSIM_PATTERN = re.compile(r"(?:qoi:dssim|external:results:dssim)<double>\s*=\s*([0-9.eE+-]+)", re.IGNORECASE)
APP_EVAL_PATTERN = re.compile(
    r"(?:external:results:app_eval_sec<[^>]+>\s*=\s*|external:app_eval_sec=)([0-9.eE+-]+)",
    re.IGNORECASE,
)


def output_csv_path(output_dir: str, compressor: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    return os.path.join(output_dir, f"{compressor}_dssim.csv")


def main():
    parser = argparse.ArgumentParser(
        description="Run pressio + DSSIM external metric and write results to CSV"
    )
    parser.add_argument("--input", "-i", required=True, help="Input .dat file (raw float)")
    parser.add_argument("--dims", nargs="+", required=True, help="Dimensions (e.g. 3600 1800)")
    parser.add_argument("--error-bounds", nargs="+", required=True, help="Error bounds (e.g. 1e-3)")
    parser.add_argument("--compressor", default="sz3")
    parser.add_argument("--output-dir", "-o", required=True,
                        help="Output folder; CSV name: <compressor>_dssim.csv")
    parser.add_argument("--datatype", "-d", default="float", help="Data type for pressio -t")
    parser.add_argument("--pressio-opts", action="append", default=[],
                        help="Extra pressio options as key=value. Can repeat.")
    args = parser.parse_args()

    output_csv = output_csv_path(args.output_dir, args.compressor)
    print(f"[DSSIM] Writing results to {output_csv}")

    fieldnames = ["compressor name", "input", "error_bound", "dssim", "app_eval_sec"] + QOI_KEYS

    def norm(v):
        try:
            return "{:.12g}".format(float(v))
        except Exception:
            return str(v).strip() if v is not None else ""

    def has_complete_qoi(row):
        # Recompute when any QoI column or app_eval_sec is missing.
        # dssim can be absent for pipeline outputs that return distance vectors.
        required = ["app_eval_sec"] + list(QOI_KEYS)
        for k in required:
            v = row.get(k, "")
            if v is None:
                return False
            if isinstance(v, str) and not v.strip():
                return False
        return True

    old_rows = []
    if os.path.exists(output_csv):
        try:
            with open(output_csv, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                fn = reader.fieldnames or []
                old_rows = list(reader)
                for k in fn:
                    if k not in fieldnames:
                        fieldnames.append(k)
        except Exception:
            old_rows = []

    index = {}
    for row in old_rows:
        comp = str(row.get("compressor name", "")).strip()
        inp = str(row.get("input", "")).strip()
        eb_val = norm(row.get("error_bound", ""))
        if comp and inp and eb_val:
            index[(comp, inp, eb_val)] = row

    compressor_name = args.compressor
    input_basename = os.path.basename(args.input)
    added_rows = 0
    updated_rows = 0

    # 调用 pressio 时去掉 PYTHONPATH，这样 external 子进程（dssim-env 的 python）不会加载 libpressio-env 的包
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    external_cmd = f"{DSSIM_PYTHON} {DSSIM_EXTERNAL}" if os.path.isfile(DSSIM_PYTHON) else f"python {DSSIM_EXTERNAL}"

    for eb in args.error_bounds:
        key = (compressor_name, input_basename, norm(eb))
        if key in index:
            if has_complete_qoi(index[key]):
                print(f"[DSSIM] skip existing compressor={compressor_name} input={input_basename} error_bound={eb}")
                continue
            print(
                f"[DSSIM] recompute missing QOI compressor={compressor_name} "
                f"input={input_basename} error_bound={eb}"
            )

        print(f"[DSSIM] {input_basename} | rel={eb}")

        cmd = [
            PRESSIO,
            "-i", os.path.abspath(args.input),
            "-T", "posix",
            "-b", f"compressor={args.compressor}",
            "-t", args.datatype,
            "-o", f"rel={eb}",
        ]
        for d in args.dims:
            cmd += ["-d", d]
        for opt in args.pressio_opts:
            cmd += ["-o", opt]
        cmd += [
            "-b", "qoi:metric=external",
            "-o", f"external:command={external_cmd}",
            "-o", "external:use_many=1",
            "-m", "qoi", "-M", "all",
        ]

        dssim_dir = os.path.dirname(DSSIM_EXTERNAL)
        print("Command (pressio_dssim):", " ".join(cmd))
        t0 = time.perf_counter()
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=dssim_dir,
            env=env,
        )
        wall_eval_sec = time.perf_counter() - t0

        if proc.returncode != 0:
            print(f"[ERROR] pressio failed for eb={eb}", file=sys.stderr)
            if proc.stderr:
                print(proc.stderr, file=sys.stderr)
            continue

        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        app_matches = APP_EVAL_PATTERN.findall(combined)
        app_eval_sec = float(app_matches[-1]) if app_matches else wall_eval_sec

        row = {
            "compressor name": args.compressor,
            "input": input_basename,
            "error_bound": eb,
            "app_eval_sec": app_eval_sec,
        }
        matches = DSSIM_PATTERN.findall(combined)
        row["dssim"] = float(matches[-1]) if matches else None
        if row["dssim"] is None and key not in index:
            print(f"[WARN] Missing dssim for eb={eb}")

        for qkey in QOI_KEYS:
            # Support both logger-style output and pressio metric output:
            # [QOI]   mean: 1.23
            # qoi:mean<double> = 1.23
            pattern = (
                r"(?:\[QOI\]\s+" + re.escape(qkey) + r"\s*:\s*|"
                r"qoi:" + re.escape(qkey) + r"<[^>]+>\s*=\s*|"
                r"external:results:" + re.escape(qkey) + r"<[^>]+>\s*=\s*)"
                r"([0-9.eE+-]+)"
            )
            qmatches = re.findall(pattern, combined, flags=re.IGNORECASE)
            row[qkey] = float(qmatches[-1]) if qmatches else None

        if key in index:
            for k, v in row.items():
                if v is not None:
                    index[key][k] = v
            updated_rows += 1
        else:
            full_row = {k: row.get(k, "") for k in fieldnames}
            old_rows.append(full_row)
            index[key] = full_row
            added_rows += 1

        # Persist every datapoint immediately to avoid losing progress on interruption.
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for existing_row in old_rows:
                for k in fieldnames:
                    if k not in existing_row:
                        existing_row[k] = ""
                writer.writerow(existing_row)

    print(f"[DSSIM] Done. Results written to {output_csv} | updated={updated_rows}, added={added_rows}")


if __name__ == "__main__":
    main()
