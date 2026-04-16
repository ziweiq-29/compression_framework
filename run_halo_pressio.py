#!/usr/bin/env python3
import subprocess
import argparse
import csv
import re
import os
import sys

# HALO pipeline 脚本
HALO_PYTHON = "/anvil/projects/x-cis240669/halo/halo_env/bin/python"
HALO_PIPELINE = os.path.expanduser("/anvil/projects/x-cis240669/halo/run_pressio_pipeline.py")
PRESSIO = "/anvil/projects/x-cis240669/libpressio-env/.spack-env/view/bin/pressio"
# ======================
# QOI regex patterns
# ======================
# Emitted by halo/run_pressio_pipeline.py (wall time of halo_dual_pressio subprocess only).
HALO_APP_EVAL_RE = re.compile(
    r"\[HALO_APP\]\s+app_eval_sec=([0-9.eE+-]+)", re.IGNORECASE
)

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

    fieldnames = ["compressor name", "input", "error_bound", "app_eval_sec"] + list(
        QOI_PATTERNS.keys()
    )

    # 数值标准化，避免 1e-1 != 0.1（与 main.py append_result_to_csv 一致）
    def norm(v):
        try:
            return "{:.12g}".format(float(v))
        except Exception:
            return str(v).strip() if v is not None else ""

    # 读取已有 CSV，按 (compressor name, input, error_bound) 建索引
    old_header, old_rows = [], []
    if os.path.exists(output_csv):
        try:
            with open(output_csv, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                old_header = reader.fieldnames or []
                old_rows = list(reader)
        except Exception:
            old_header, old_rows = [], []

    # 已存在行的 key = (compressor name, input, norm(error_bound))
    index = {}
    for row in old_rows:
        comp = str(row.get("compressor name", "")).strip()
        inp = str(row.get("input", "")).strip()
        eb_val = norm(row.get("error_bound", ""))
        if comp and inp and eb_val:
            index[(comp, inp, eb_val)] = row

    def has_app_eval_sec(row: dict) -> bool:
        v = row.get("app_eval_sec", "")
        if v is None:
            return False
        if isinstance(v, str) and not str(v).strip():
            return False
        return True

    compressor_name = args.compressor
    input_basename = os.path.basename(args.input)
    added_rows = 0
    updated_rows = 0

    for eb in args.error_bounds:
        key = (compressor_name, input_basename, norm(eb))
        if key in index and has_app_eval_sec(index[key]):
            print(
                f"[HALO] skip existing compressor={compressor_name} input={input_basename} error_bound={eb}"
            )
            continue

        print(f"[HALO] {input_basename} | rel={eb}")

        # 与手动 pressio 命令一致：minimal external:command，pressio 自动注入 --input --decompressed --dim 等
        input_dir = os.path.abspath(args.input)
        external_cmd = f"env -u PYTHONPATH {HALO_PYTHON} {HALO_PIPELINE} --external_mode"
        cmd = [
            PRESSIO,
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

        halo_dir = os.path.dirname(HALO_PIPELINE)
        print("Command (pressio_halo)", " ".join(cmd))
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

        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")

        app_chunks = [float(m) for m in HALO_APP_EVAL_RE.findall(combined)]
        if app_chunks:
            app_eval_total = sum(app_chunks)
            app_eval_str = "{:.15g}".format(app_eval_total)
        else:
            app_eval_str = ""
            print(
                "[WARN] No [HALO_APP] app_eval_sec lines in pressio output "
                f"(eb={eb}); update halo/run_pressio_pipeline.py?",
                file=sys.stderr,
            )

        # Parse QOI output (pressio may print [QOI] to stdout or stderr)
        row = {
            "compressor name": args.compressor,
            "input": os.path.basename(args.input),
            "error_bound": eb,
            "app_eval_sec": app_eval_str,
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
            dump = os.environ.get("HALO_DEBUG_QOI")
            if dump:
                snippet = combined[:4000] if len(combined) > 4000 else combined
                print(f"[DEBUG] pressio combined output (first {len(snippet)} chars):", file=sys.stderr)
                sys.stderr.write(snippet)
                if len(combined) > 4000:
                    print("\n... (truncated)", file=sys.stderr)

        # 合并到 old_rows：若 key 已存在则更新，否则追加（与 main.py 一致）
        key = (compressor_name, input_basename, norm(eb))
        if key in index:
            for k, v in row.items():
                if v is not None and v != "":
                    index[key][k] = v
            updated_rows += 1
        else:
            full_row = {k: row.get(k, "") for k in fieldnames}
            old_rows.append(full_row)
            index[key] = full_row
            added_rows += 1

    # 写回完整 CSV
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in old_rows:
            for k in fieldnames:
                if k not in row:
                    row[k] = ""
            writer.writerow(row)

    print(f"[HALO] Done. Results written to {output_csv} | updated={updated_rows}, added={added_rows}")


if __name__ == "__main__":
    main()
