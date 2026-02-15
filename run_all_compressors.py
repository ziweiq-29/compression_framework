import subprocess
import glob
import os
import shutil
import sys

# 通用参数
dims = "512 512 512"
datatype = "f"
mode = "REL"
# qcat_evaluators = "compareData,ssim,computeErrAutoCorrelation"
# qcat_evaluators = "ssim"
# qcat_evaluators = "compareData,ssim,computeErrAutoCorrelation"
# error_bounds = ["1e-1", "5e-2", "1e-2", "5e-3", "1e-3", "5e-4", "1e-4", "5e-5", "1e-5", "5e-6", "1e-6"]
error_bounds = ["1e-1", "5e-2"]
error_bounds_tthresh = [float(e) for e in error_bounds]
# 根目录
root_dir = "dataset/NYX"
# compressors = ["sperr3d","sz3","faz","qoz","tthresh","zfp"]
compressors = ["sperr"]
# 输出根目录：outputs/HALO，其下与 main 一致为 <dataset>/<var_dir>
output_root = "outputs/HALO"
# dims = len(dims.split())

# 只跑前 N 个文件；设为 None 则跑全部
MAX_FILES = 1
_file_list = sorted(os.listdir(root_dir))
if MAX_FILES is not None:
    _file_list = _file_list[:MAX_FILES]
    
# for fname in root_dir:

for fname in _file_list:
    if "log10" in fname:
        print(f"[SKIP] Skipping {fname} because it contains 'log10'")
        continue
    for compressor in compressors:

        input_path = os.path.join(root_dir, fname)
        print(f"\n=== Running {compressor} on {fname} ===")

        # 与 main.py 一致：output_root/<dataset>/<input_base><suffix>
        dataset_name = os.path.basename(os.path.normpath(root_dir))
        input_base, ext = os.path.splitext(fname)
        suffix = f"_{ext[1:].lower()}" if ext else ""
        var_dir = input_base + suffix
        output_dir = os.path.join(output_root, dataset_name, var_dir)
        for f in glob.glob("tmp_*.compressed") + glob.glob("tmp_*.out"):
            os.remove(f)

        cmd = [
            "python", "main.py",
            "--compressor", compressor,
            "--mode", mode,
            "--dims", dims,
            "--input", input_path,
            "--datatype", datatype,
            "--enable-qcat",
            "--sweep", *error_bounds,
            "--output-dir", output_root,
        ]

        halo_datatype = "float" if datatype == "f" else "double"
        cmd_halo = [
            "python", "run_halo_pressio.py",
            "--input", input_path,
            "--dims", *dims.split(),
            "--error-bounds", *error_bounds,
            "--compressor", compressor,
            "--datatype", halo_datatype,
            "--output-dir", output_dir,
        ]
        
        
        try:
            # print("Command (main):", " ".join(cmd))
            # subprocess.run(cmd, check=True)
            print("Command (halo):", " ".join(cmd_halo))
            subprocess.run(cmd_halo, check=True)
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Failed on {fname}. Skipping.")
            print(e)
