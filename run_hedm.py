#!/usr/bin/env python3
"""Run pressio + HEDM external QOI and write results to CSV (same logic as run_halo_pressio.py)."""
import argparse
import csv
import fcntl
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager

PRESSIO = "/anvil/projects/x-cis240669/libpressio-env/.spack-env/view/bin/pressio"
HEDM_EXTERNAL = "/anvil/projects/x-cis240669/MIDAS/FF_HEDM/workflows/hedm_external.py"
MIDAS_PYTHON = "/anvil/projects/x-cis240669/MIDAS/midas_env/bin/python"
HEDM_EXTERNAL_DEFAULT_ARGS = [
    "-nCPUs", "96",
    "-preProcThresh", "70",
    "-numFrameChunks", "100",
    "-peakSearchOnly", "1",
]

QOI_PATTERNS = {
    "mean": r"\[QOI\]\s+mean\s*:\s*([0-9.eE+-]+)",
    "min": r"\[QOI\]\s+min\s*:\s*([0-9.eE+-]+)",
    "max": r"\[QOI\]\s+max\s*:\s*([0-9.eE+-]+)",
    "median": r"\[QOI\]\s+median\s*:\s*([0-9.eE+-]+)",
    "p90": r"\[QOI\]\s+p90\s*:\s*([0-9.eE+-]+)",
    "p99": r"\[QOI\]\s+p99\s*:\s*([0-9.eE+-]+)",
    "p999": r"\[QOI\]\s+p999\s*:\s*([0-9.eE+-]+)",
    "wasserstein_distance": r"\[QOI\]\s+wasserstein_distance\s*:\s*([0-9.eE+-]+)",
}


def output_csv_path(output_dir: str, compressor: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    return os.path.join(output_dir, f"{compressor}_hedm.csv")


@contextmanager
def _csv_lock(csv_path: str):
    lock_path = csv_path + ".lock"
    with open(lock_path, "w", encoding="utf-8") as lockf:
        fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)


def _load_rows(csv_path: str):
    rows = []
    if os.path.exists(csv_path):
        try:
            with open(csv_path, "r", newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        except Exception:
            rows = []
    return rows


def _build_index(rows, norm_func):
    idx = {}
    for row in rows:
        comp = str(row.get("compressor name", "")).strip()
        inp = str(row.get("input", "")).strip()
        eb_val = norm_func(row.get("error_bound", ""))
        if comp and inp and eb_val:
            idx[(comp, inp, eb_val)] = row
    return idx


def _write_rows(csv_path: str, rows, fieldnames):
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            for k in fieldnames:
                if k not in row:
                    row[k] = ""
            writer.writerow(row)


def _preferred_tmp_base(fallback_dir: str) -> str:
    tmp_dir = os.environ.get("TMPDIR", "").strip()
    if tmp_dir and os.path.isdir(tmp_dir) and os.access(tmp_dir, os.W_OK | os.X_OK):
        return tmp_dir
    return fallback_dir


def main():
    parser = argparse.ArgumentParser(
        description="Run pressio + HEDM external QOI and write results to CSV"
    )
    parser.add_argument("--input", "-i", required=True, help="Input float32 raw payload file")
    parser.add_argument(
        "--header-source",
        default="",
        help="Original .edf.ge5 file used by external script for header bytes",
    )
    parser.add_argument("--dims", nargs="+", required=True, help="Dimensions (e.g. 1441 2048 2048)")
    parser.add_argument("--error-bounds", nargs="+", required=True, help="Error bounds (e.g. 1e-3)")
    parser.add_argument("--compressor", default="sz3")
    parser.add_argument("--output-dir", "-o", required=True,
                        help="Output folder; CSV name: <compressor>_hedm.csv")
    parser.add_argument("--pressio-opts", action="append", default=[],
                        help="Extra pressio options as key=value. Can repeat.")
    args = parser.parse_args()

    output_csv = output_csv_path(args.output_dir, args.compressor)
    print(f"[HEDM] Writing results to {output_csv}")

    fieldnames = ["compressor name", "input", "error_bound"] + list(QOI_PATTERNS.keys())

    def norm(v):
        try:
            return "{:.12g}".format(float(v))
        except Exception:
            return str(v).strip() if v is not None else ""

    compressor_name = args.compressor
    input_basename = os.path.basename(args.input)
    added_rows = 0
    updated_rows = 0

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    if os.path.isfile(MIDAS_PYTHON):
        env["MIDAS_PYTHON"] = MIDAS_PYTHON
    if args.header_source:
        env["HEDM_HEADER_SOURCE"] = os.path.abspath(args.header_source)
    hedm_dir = os.path.dirname(HEDM_EXTERNAL)
    tmp_base = _preferred_tmp_base(hedm_dir)

    for eb in args.error_bounds:
        key = (compressor_name, input_basename, norm(eb))
        with _csv_lock(output_csv):
            existing_rows = _load_rows(output_csv)
            existing_index = _build_index(existing_rows, norm)
            if key in existing_index:
                print(f"[HEDM] skip existing compressor={compressor_name} input={input_basename} error_bound={eb}")
                continue

        print(f"[HEDM] {input_basename} | rel={eb}")
        eb_tag = str(eb).replace(".", "p").replace("-", "m")
        result_folder = tempfile.mkdtemp(
            prefix=f"hedm_{compressor_name}_{eb_tag}_",
            dir=tmp_base,
        )

        cmd = [
            PRESSIO,
            "-i", os.path.abspath(args.input),
            "-T", "posix",
            "-b", f"compressor={args.compressor}",
            "-t", "float",
            "-o", f"rel={eb}",
        ]
        for d in args.dims:
            cmd += ["-d", d]
        for opt in args.pressio_opts:
            cmd += ["-o", opt]
        external_command_parts = (
            ["env", "-u", "PYTHONPATH", "python", HEDM_EXTERNAL]
            + HEDM_EXTERNAL_DEFAULT_ARGS
            + ["-resultFolder", result_folder]
        )
        external_command = " ".join(shlex.quote(x) for x in external_command_parts)
        cmd += [
            "-b", "qoi:metric=external",
            "-o", f"external:command={external_command}",
            "-o", "external:use_many=1",
            "-m", "qoi", "-M", "all",
        ]

        print("Command (pressio_hedm):", " ".join(cmd))
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=hedm_dir,
                env=env,
            )
        finally:
            # Avoid cross-datapoint interference by cleaning ff_MIDAS outputs per run.
            shutil.rmtree(result_folder, ignore_errors=True)

        if proc.returncode != 0:
            print(f"[ERROR] pressio failed for eb={eb}", file=sys.stderr)
            if proc.stderr:
                print(proc.stderr, file=sys.stderr)
            if proc.stdout:
                print(proc.stdout[-4000:], file=sys.stderr)
            continue

        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")

        row = {
            "compressor name": args.compressor,
            "input": input_basename,
            "error_bound": eb,
        }
        missing = False
        for qkey, pattern in QOI_PATTERNS.items():
            matches = re.findall(pattern, combined)
            if matches:
                row[qkey] = float(matches[-1])
            else:
                row[qkey] = None
                missing = True
                print(f"[WARN] Missing QOI field '{qkey}' for eb={eb}")
        if missing:
            print("[WARN] Incomplete QOI row written to CSV")

        with _csv_lock(output_csv):
            existing_rows = _load_rows(output_csv)
            existing_index = _build_index(existing_rows, norm)
            if key in existing_index:
                for k, v in row.items():
                    if v is not None:
                        existing_index[key][k] = v
                updated_rows += 1
            else:
                full_row = {k: row.get(k, "") for k in fieldnames}
                existing_rows.append(full_row)
                added_rows += 1
            _write_rows(output_csv, existing_rows, fieldnames)

    print(f"[HEDM] Done. Results written to {output_csv} | updated={updated_rows}, added={added_rows}")


if __name__ == "__main__":
    main()
