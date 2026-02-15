#!/usr/bin/env python3
import subprocess
import argparse
import csv
import re
import os
import sys

# HALO pipeline 脚本
HALO_PIPELINE = os.path.expanduser("/home/ziweiq2/halo/run_pressio_pipeline.py")

# ======================
# QOI regex patterns
# ======================
QOI_PATTERNS = {
    "mean": r"\[QOI\]\s+mean:\s+([0-9.eE+-]+)",
    "min": r"\[QOI\]\s+min:\s+([0-9.eE+-]+)",
    "max": r"\[QOI\]\s+max:\s+([0-9.eE+-]+)",
    "median": r"\[QOI\]\s+median:\s+([0-9.eE+-]+)",
    "p90": r"\[QOI\]\s+p90:\s+([0-9.eE+-]+)",
    "p99": r"\[QOI\]\s+p99:\s+([0-9.eE+-]+)",
    "p999": r"\[QOI\]\s+p999:\s+([0-9.eE+-]+)",
    "wasserstein_distance": r"\[QOI\]\s+wasserstein_distance:\s+([0-9.eE+-]+)",
}

def output_csv_path(output_dir: str, compressor: str) -> str:
    """You pass the full folder path (same as main). We only build CSV name: <compressor>_halo.csv"""
    os.makedirs(output_dir, exist_ok=True)
    return os.path.join(output_dir, f"{compressor}_halo.csv")


def main():
    parser = argparse.ArgumentParser(
        description="Run pressio + HALO external QOI and write results to CSV"
    )
    parser.add_argument("--input", required=True, help="Input data file")
    parser.add_argument("--dims", nargs="+", required=True, help="Data dimensions")
    parser.add_argument("--error-bounds", nargs="+", required=True, help="Error bounds")
    parser.add_argument("--compressor", default="sz3")
    parser.add_argument("--datatype", default="float")
    parser.add_argument("--output-dir", "-o", required=True,
                        help="Full path to output folder (same as main's output_dir). CSV name: <compressor>_halo.csv")

    args = parser.parse_args()

    output_csv = output_csv_path(args.output_dir, args.compressor)

    print(f"[HALO] Writing results to {output_csv}")

    # 每次运行都重写 CSV，而不是在原文件后追加
    with open(output_csv, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["compressor name", "input", "error_bound"] + list(QOI_PATTERNS.keys()),
        )
        writer.writeheader()
        for eb in args.error_bounds:
            print(f"[HALO] {os.path.basename(args.input)} | rel={eb}")

            # 与手动 pressio 命令一致：minimal external:command，pressio 自动注入 --input --decompressed --dim 等
            input_dir = os.path.abspath(args.input)
            external_cmd = f"python {HALO_PIPELINE} --external_mode"

            cmd = [
                "pressio",
                "-i", input_dir,
                "-b", f"compressor={args.compressor}",
                "-o", f"rel={eb}",
            ]
            input_lower = input_dir.lower()
            if input_lower.endswith(".h5") or input_lower.endswith(".hdf5"):
                cmd += ["-I", "/native_fields/baryon_density"]
            for d in args.dims:
                cmd += ["-d", d]
            cmd += [
                "-t", args.datatype,
                "-b", "qoi:metric=external",
                "-o", f"external:command={external_cmd}",
                "-b", "external:launch_metric=print",
                "-o", "external:use_many=1",
                "-m", "qoi",
                "-M", "all",
            ]

            # 与手动一致：在 halo 目录下跑 pressio，避免 cwd 导致 temp 文件或 external 行为不一致
            halo_dir = os.path.dirname(HALO_PIPELINE)
            print("Command (pressio)", " ".join(cmd))
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=halo_dir,
            )

            if proc.returncode != 0:
                print(f"[ERROR] pressio failed for eb={eb}", file=sys.stderr)
                print(proc.stderr, file=sys.stderr)
                continue

            stdout = proc.stdout

            # ----------------------
            # Parse QOI output
            # ----------------------
            row = {
                "compressor name": args.compressor,
                "input": os.path.basename(args.input),
                "error_bound": eb,
            }

            missing = False
            for key, pattern in QOI_PATTERNS.items():
                matches = re.findall(pattern, stdout)
                if matches:
                    row[key] = float(matches[-1])
                else:
                    row[key] = None
                    missing = True
                    print(f"[WARN] Missing QOI field '{key}' for eb={eb}")

            if missing:
                print("[WARN] Incomplete QOI row written to CSV")

            writer.writerow(row)
            f.flush()

    print(f"[HALO] Done. Results written to {output_csv}")


if __name__ == "__main__":
    main()
