#!/usr/bin/env python3
"""Run pressio + HEDM external QOI and write results to CSV (same logic as run_halo_pressio.py)."""
import argparse
import csv
import fcntl
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
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
DEFAULT_PRESSIO_TIMEOUT_SEC = 30 * 60
DEFAULT_EXTERNAL_NUM_THREADS = 1

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
    if os.path.isdir("/tmp") and os.access("/tmp", os.W_OK | os.X_OK):
        return "/tmp"
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
    parser.add_argument(
        "--pressio-timeout-sec",
        type=int,
        default=DEFAULT_PRESSIO_TIMEOUT_SEC,
        help=f"Timeout per error bound (seconds). 0 disables timeout. default={DEFAULT_PRESSIO_TIMEOUT_SEC}",
    )
    parser.add_argument(
        "--external-num-threads",
        type=int,
        default=DEFAULT_EXTERNAL_NUM_THREADS,
        help=f"Thread cap for external numpy/BLAS runtime. default={DEFAULT_EXTERNAL_NUM_THREADS}",
    )
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
    if args.external_num_threads > 0:
        thread_count = str(args.external_num_threads)
        for var in (
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
            "BLIS_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS",
        ):
            env[var] = thread_count
    hedm_dir = os.path.dirname(HEDM_EXTERNAL)
    tmp_base = _preferred_tmp_base(hedm_dir)
    env.setdefault("TMPDIR", tmp_base)

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
        print(f"[HEDM] resultFolder={result_folder}")
        pressio_run_dir = tempfile.mkdtemp(
            prefix=f"pressio_{compressor_name}_{eb_tag}_",
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
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                cwd=pressio_run_dir,
                env=env,
                start_new_session=True,
            )
            timeout = args.pressio_timeout_sec if args.pressio_timeout_sec > 0 else None
            try:
                out_text, err_text = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                print(
                    f"[ERROR] pressio timeout for eb={eb} after {args.pressio_timeout_sec}s; killing process group",
                    file=sys.stderr,
                )
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except Exception:
                    pass
                time.sleep(5)
                if proc.poll() is None:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except Exception:
                        pass
                out_text, err_text = proc.communicate()
        finally:
            # Avoid cross-datapoint interference by cleaning ff_MIDAS outputs per run.
            # NOTE: user debugging request: keep `result_folder` for inspection.
            # shutil.rmtree(result_folder, ignore_errors=True)
            shutil.rmtree(pressio_run_dir, ignore_errors=True)

        if proc.returncode != 0:
            print(f"[ERROR] pressio failed for eb={eb}", file=sys.stderr)
            if err_text:
                print(err_text, file=sys.stderr)
            if out_text:
                print(out_text[-4000:], file=sys.stderr)
            continue

        combined = (out_text or "") + "\n" + (err_text or "")

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
