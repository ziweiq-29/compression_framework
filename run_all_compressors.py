import subprocess
import glob
import os

# 通用参数
dims = "1200 1200 98"
datatype = "f"
mode = "REL"
# qcat_evaluators = "compareData,ssim,computeErrAutoCorrelation"
# qcat_evaluators = "ssim"
# qcat_evaluators = "compareData,ssim,computeErrAutoCorrelation"
error_bounds = ["1e-1", "5e-2", "1e-2", "5e-3", "1e-3", "5e-4", "1e-4", "5e-5", "1e-5", "5e-6", "1e-6"]
error_bounds_tthresh = [float(e) for e in error_bounds]
# 根目录
root_dir = "dataset/SDRBENCH-SCALE_98x1200x1200"
# compressors = ["sperr3d","sz3","faz","qoz","tthresh","zfp"]
compressors = ["sperr3d"]

ndim = len(dims.split())

for fname in os.listdir(root_dir):
    if "log10" in fname:
        print(f"[SKIP] Skipping {fname} because it contains 'log10'")
        continue
    for compressor in compressors:
        # if not fname.endswith(".f32"):
        #     continue

        input_path = os.path.join(root_dir, fname)
        print(f"\n=== Running {compressor} on {fname} ===")

        # 删除旧的临时文件
        for f in glob.glob("tmp_*.compressed") + glob.glob("tmp_*.out"):
            os.remove(f) 

        # 构建命令
        cmd = [
            "python", "main.py",
            "--compressor", compressor,
            "--mode", mode,
            "--dims", dims,
            "--input", input_path,
            "--datatype", datatype,
            # "--enable-qcat",
            # "--qcat-evaluators", qcat_evaluators,
            # "--smooth", "inf",s
            "--sweep"
        ] + error_bounds

        print("Command:", " ".join(cmd))

        # 执行命令并捕获异常
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Failed on file {fname}.  Skipping. Error: {e}")
