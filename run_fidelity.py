#!/usr/bin/env python3
"""
Run fidelity QOI metrics sweep and write CSV.

This wrapper exists so `run_all_compressors.py` can call a stable entrypoint.
It delegates to:
  riken/extracted/output_stata_vectors/sweep_error_bound_fidelity.py

That script (via delegation) parses qoi.cc printed metrics like:
  [QOI] wasserstein_distance: ...
  [QOI] fidelity: ...
and writes them to CSV.
"""

import argparse
import os
import subprocess
import sys


_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RKEN_SWEEP = "/anvil/projects/x-cis240669/riken/extracted/output_stata_vectors/sweep_error_bound_fidelity.py"
DEFAULT_PRESSIO = "/anvil/projects/x-cis240669/libpressio-env/.spack-env/view/bin/pressio"


def parse_args():
    p = argparse.ArgumentParser(description="Run fidelity QOI sweep and write metrics CSV")
    p.add_argument("--folders", nargs="+", required=True, help="Folders containing stdout.1.0.res.npy")
    p.add_argument("--error-bounds", nargs="+", required=True, help="Error bounds, e.g. 1e-3 5e-4")
    p.add_argument("--compressor", default="sz3", help="Compressor name for compress_parallel.py")
    p.add_argument("--error-option", default="auto", help="compress_parallel error-option key")
    p.add_argument("--output-dir", "-o", required=True, help="Output root directory; per-folder subdir will be created")
    p.add_argument("--csv-name", default=None, help="CSV filename (default: <compressor>_fidelity.csv)")
    p.add_argument("--python", default=sys.executable, help="Python executable for child scripts")
    p.add_argument("--pressio-bin", default=DEFAULT_PRESSIO, help="pressio executable path")
    p.add_argument("--no-force", action="store_true", help="Do not pass --force to compress_parallel.py")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not os.path.isfile(RKEN_SWEEP):
        print(f"[ERROR] missing: {RKEN_SWEEP}", file=sys.stderr)
        return 1

    output_root = os.path.abspath(args.output_dir)
    csv_name = args.csv_name or f"{args.compressor}_fidelity.csv"

    # For compatibility with sweep_error_bound_* scripts (which produce one CSV),
    # run the sweep separately per folder so the output layout matches:
    #   <output_root>/<folder_basename>/<csv_name>
    for folder in args.folders:
        folder_abs = folder if os.path.isabs(folder) else os.path.abspath(folder)
        folder_base = os.path.basename(folder_abs.rstrip(os.sep))
        out_dir = os.path.join(output_root, folder_base)
        os.makedirs(out_dir, exist_ok=True)
        csv_path = os.path.join(out_dir, csv_name)

        cmd = [
            args.python,
            RKEN_SWEEP,
            "--folders",
            folder_abs,
            "--error-bounds",
            *args.error_bounds,
            "--compressor",
            args.compressor,
            "--error-option",
            args.error_option,
            "--pressio-bin",
            args.pressio_bin,
            "--csv",
            csv_path,
            "--python",
            args.python,
        ]
        if args.no_force:
            cmd.append("--no-force")

        print("[run_fidelity] Running:", " ".join(cmd), flush=True)
        subprocess.run(cmd, check=True, cwd=_SCRIPT_DIR)
        print(f"[run_fidelity] Done. CSV={csv_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

