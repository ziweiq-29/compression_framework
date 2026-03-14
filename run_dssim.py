#!/usr/bin/env python3
"""Run pressio + DSSIM external metric and write results to CSV (same logic as run_hedm.py)."""
import argparse
import csv
import os
import re
import subprocess
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PRESSIO = "/anvil/projects/x-cis240669/libpressio-env/.spack-env/view/bin/pressio"
DSSIM_EXTERNAL = "/anvil/projects/x-cis240669/DSSIM/pressio_dssim.py"
DSSIM_PYTHON = "/anvil/projects/x-cis240669/DSSIM/dssim-env/bin/python"

# Parse from pressio output: external:results:dssim<double> = 2.37319e-06
DSSIM_PATTERN = re.compile(
    r"external:results:dssim<double>\s*=\s*([0-9.eE+-]+)",
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

    fieldnames = ["compressor name", "input", "error_bound", "dssim"]

    def norm(v):
        try:
            return "{:.12g}".format(float(v))
        except Exception:
            return str(v).strip() if v is not None else ""

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
            print(f"[DSSIM] skip existing compressor={compressor_name} input={input_basename} error_bound={eb}")
            continue

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
            "-b", "external:launch_metric=print",
            "-o", "external:use_many=1",
            "-m", "qoi", "-M", "all",
        ]

        dssim_dir = os.path.dirname(DSSIM_EXTERNAL)
        print("Command (pressio_dssim):", " ".join(cmd))
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=dssim_dir,
            env=env,
        )

        if proc.returncode != 0:
            print(f"[ERROR] pressio failed for eb={eb}", file=sys.stderr)
            if proc.stderr:
                print(proc.stderr, file=sys.stderr)
            continue

        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")

        row = {
            "compressor name": args.compressor,
            "input": input_basename,
            "error_bound": eb,
        }
        matches = DSSIM_PATTERN.findall(combined)
        if matches:
            row["dssim"] = float(matches[-1])
        else:
            row["dssim"] = None
            print(f"[WARN] Missing dssim for eb={eb}")

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

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in old_rows:
            for k in fieldnames:
                if k not in row:
                    row[k] = ""
            writer.writerow(row)

    print(f"[DSSIM] Done. Results written to {output_csv} | updated={updated_rows}, added={added_rows}")


if __name__ == "__main__":
    main()
