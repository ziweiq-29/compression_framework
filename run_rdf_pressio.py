#!/usr/bin/env python3
import argparse
import csv
import os
import re
import subprocess
import sys
from datetime import datetime

# === 固定路径（按你现在的环境） ===
RDF_DIR = os.path.expanduser("/anvil/projects/x-cis240669/RDF")
RDF_PIPELINE = os.path.join(RDF_DIR, "run_pressio_external.py")
RDF_PYTHON = "/anvil/projects/x-cis240669/RDF/rdf_env/bin/python"
PRESSIO = "/anvil/projects/x-cis240669/libpressio-env/.spack-env/view/bin/pressio"

# === 只解析 pressio 输出的 [QOI] 行（不做计算）===
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
    return os.path.join(output_dir, f"{compressor}_rdf.csv")

def write_debug_log(output_dir: str, compressor: str, eb: str, text: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(output_dir, f"debug_qoi_{compressor}_rel{eb}_{ts}.log")
    with open(path, "w") as f:
        f.write(text)
    return path

def parse_qoi_from_text(text: str):
    """只解析，不计算。取每个字段最后一次出现的值。"""
    out = {}
    for k, pat in QOI_PATTERNS.items():
        m = re.findall(pat, text)
        out[k] = float(m[-1]) if m else None
    return out

def main():
    ap = argparse.ArgumentParser(description="Run RDF external and parse [QOI] lines into CSV (no computation).")
    ap.add_argument("--input", required=True, help="Prefix path (no .x/.y/.z suffix), e.g. .../10x32000")
    ap.add_argument("--dims", nargs="+", required=True, help="Dims: nt na")
    ap.add_argument("--error-bounds", nargs="+", required=True, help="Error bounds list, e.g. 1e-3 5e-4")
    ap.add_argument("--compressor", default="sz3")
    ap.add_argument("--datatype", default="float")  # 保留接口，当前不用
    ap.add_argument("--output-dir", "-o", required=True, help="Output folder; CSV name is <compressor>_rdf.csv")
    ap.add_argument("--pressio-opts", action="append", default=[],
                    help='Forward to run_pressio_external.py. Can repeat. Example: --pressio-opts "sz3:algorithm_str=ALGO_BIOMD"')
    ap.add_argument("--print-output-on-fail", action="store_true",
                    help="If QOI missing, also print last ~2000 chars to stderr for quick glance.")
    args = ap.parse_args()

    input_prefix = os.path.abspath(args.input)
    nt, na = int(args.dims[0]), int(args.dims[1])

    output_csv = output_csv_path(args.output_dir, args.compressor)
    print(f"[RDF] Writing results to {output_csv}")

    with open(output_csv, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["compressor name", "input", "error_bound"] + list(QOI_PATTERNS.keys()),
        )
        writer.writeheader()

        for eb in args.error_bounds:
            print(f"[RDF] {os.path.basename(input_prefix)} | rel={eb}")

            cmd = [
                "env", "-u", "PYTHONPATH",
                RDF_PYTHON, RDF_PIPELINE,
                "--prefix", input_prefix,
                "--nt", str(nt),
                "--na", str(na),
                "--rel", str(eb),
                "--compressor", args.compressor,
                "--pressio-cmd", PRESSIO,
            ]
            for opt in args.pressio_opts:
                cmd += ["--pressio-opts", opt]

            # 重要：stdout/stderr 都抓住，合并后解析
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=RDF_DIR,
            )

            combined = (proc.stdout or "") + "\n" + (proc.stderr or "")

            if proc.returncode != 0:
                print(f"[ERROR] RDF pipeline failed for eb={eb}", file=sys.stderr)
                log_path = write_debug_log(args.output_dir, args.compressor, str(eb), combined)
                print(f"[ERROR] Full output saved to: {log_path}", file=sys.stderr)
                continue

            qoi = parse_qoi_from_text(combined)

            row = {
                "compressor name": args.compressor,
                "input": os.path.basename(input_prefix),
                "error_bound": eb,
                **qoi,
            }

            missing = [k for k, v in qoi.items() if v is None]
            if missing:
                print(f"[WARN] Missing QOI field(s): {missing}")
                log_path = write_debug_log(args.output_dir, args.compressor, str(eb), combined)
                print(f"[WARN] Full output saved to: {log_path}")
                if args.print_output_on_fail:
                    tail = combined[-2000:] if len(combined) > 2000 else combined
                    print("----- output tail -----", file=sys.stderr)
                    print(tail, file=sys.stderr)
                    print("-----------------------", file=sys.stderr)

            writer.writerow(row)
            f.flush()

    print(f"[RDF] Done. Results written to {output_csv}")

if __name__ == "__main__":
    main()