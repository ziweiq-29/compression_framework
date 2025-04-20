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

files = sorted(f for f in os.listdir(args.dataset_dir)
               if os.path.isfile(os.path.join(args.dataset_dir, f)))


for fname in files:
    input_path = os.path.join(args.dataset_dir, fname)
    output_csv = os.path.join(args.results_dir, fname + ".csv")


    cmd = [
        "python", "main.py",
        "--compressor", args.compressor,
        "--mode", args.mode,
        "--dims", args.dims,
        "--input", input_path
    ]

    if args.sweep:
        cmd.extend(["--sweep", *args.sweep])
    elif args.value:
        cmd.extend(["--value", args.value])
    
    print(f"🔹 Running on {fname}...")
    subprocess.run(cmd, check=True)

    if os.path.exists("results.csv"):
        os.rename("results.csv", output_csv)
        print(f"✅ Saved to {output_csv}")
        df = pd.read_csv(output_csv)   # ✅ 用新文件名来读！
        df["input_file"] = fname
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