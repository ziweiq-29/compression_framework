import os
import argparse
import subprocess
import pandas as pd

# Argument parser
parser = argparse.ArgumentParser()
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument("--sweep", nargs="+", help="List of error bounds")
group.add_argument("--value", help="Single error bound")

parser.add_argument("--dataset_dir", required=True, help="Directory containing .f32 files")
parser.add_argument("--dims", required=True, help="Data dimensions, e.g. '512 512 512'")
parser.add_argument("--compressor", default="qoz", help="Compressor name")
parser.add_argument("--mode", default="REL", help="Compression mode (ABS, REL, etc.)")
parser.add_argument("--results_dir", default="results", help="Directory to save result CSVs")
parser.add_argument("--enable-qcat", action="store_true", help="Enable qcat evaluation")
parser.add_argument("--datatype", choices=["f", "d"], required=True, help="Data type (f for float, d for double)")

parser.add_argument("--enable-calc_stats", action="store_true", help="Enable calcErrStats.py evaluation")
parser.add_argument("--block-size", type=int, default=-1, help="Block size for calcErrStats.py (-1 for global)")
parser.add_argument("--shift-size", type=int, help="Shift size for blockwise calcErrStats.py (optional)")
parser.add_argument("--output-prefix", type=str, help="Output prefix for calcErrStats.py, required if block-size > 0")


parser.add_argument("--qcat-evaluators", type=str, default="ssim,compareData",
                    help="Comma-separated list of qcat evaluators to use (default: 'ssim,compareData')")
parser.add_argument(
    "--results_csv",                 
    default="results.csv",
    help="Path for the merged output CSV"
)
args = parser.parse_args()

# Accumulate all results
all_results = []

# Ensure results directory exists
os.makedirs(args.results_dir, exist_ok=True)

# 只保留非 .txt 结尾的文件（例如 .f32、.dat）
files = sorted(
    f for f in os.listdir(args.dataset_dir)
    if os.path.isfile(os.path.join(args.dataset_dir, f)) and not f.endswith(".txt")
)


# files = sorted(f for f in os.listdir(args.dataset_dir)
#                if os.path.isfile(os.path.join(args.dataset_dir, f)))

for fname in files:
    input_path = os.path.join(args.dataset_dir, fname)
    output_csv = os.path.join(args.results_dir, fname + ".csv")

    
    cmd = [
        "python", "main.py",
        "--compressor", args.compressor,
        "--mode", args.mode,
        "--dims", args.dims,
        "--input", input_path,
        "--datatype", args.datatype
    ]

    if args.sweep:
        cmd.extend(["--sweep", *args.sweep])
    elif args.value:
        cmd.extend(["--value", args.value])
        
    if args.enable_qcat:
        cmd.append("--enable-qcat")
        if args.datatype:
            cmd.extend(["--datatype", args.datatype])
        else:
            print("⚠️ --datatype is required when --enable-qcat is used.")
            continue  # Skip this file if datatype is missing
    if args.qcat_evaluators:
        cmd.extend(["--qcat-evaluators", args.qcat_evaluators])
    
    
    if args.enable_calc_stats:
        file_results_dir = os.path.join(args.results_dir, os.path.splitext(fname)[0])
        output_prefix = os.path.join(file_results_dir, os.path.splitext(fname)[0])
        os.makedirs(file_results_dir, exist_ok=True)
        cmd.append("--enable-calc_stats")
        cmd.extend([
            "--block-size", str(args.block_size),
            "--shift-size", str(args.shift_size),
            "--output-prefix", output_prefix
        ])

    print("cmd: ",cmd)
    
    print(f"🔹 Running on {fname}...")
    subprocess.run(cmd, check=True)

    if os.path.exists("results.csv"):
        os.rename("results.csv", output_csv)
        print(f"✅ Saved to {output_csv}")
        df = pd.read_csv(output_csv)   # ✅ 用新文件名来读！
        # df["input_file"] = fname
        all_results.append(df)
    else:
        print("⚠️ Warning: results.csv not found.")
# Merge and export
if all_results:
    merged = pd.concat(all_results, ignore_index=True)
    print("\n✅ Final results:")
    print(merged)
    merged.to_csv(args.results_csv, index=False)
else:
    print("❌ No results collected.")