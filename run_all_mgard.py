import subprocess
import glob
import os

# 通用参数
dims = "33120 69 69"
datatype = "f"
mode = "REL"
# qcat_evaluators = "compareData,ssim,computeErrAutoCorrelation"
# qcat_evaluators = "ssim"
qcat_evaluators = "compareData,ssim,computeErrAutoCorrelation"
error_bounds_mgard = ["1e-1", "5e-2", "1e-2", "5e-3", "1e-3", "5e-4", "1e-4", "5e-5", "1e-5", "5e-6", "1e-6"]

# 根目录
root_dir = "dataset/288x115x69x69"
compressor = "mgard"


for fname in os.listdir(root_dir):
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
        "--enable-qcat",
        "--qcat-evaluators", qcat_evaluators,
        "--smooth", "inf",
        "--sweep"
    ] + error_bounds_mgard

    print("Command:", " ".join(cmd))

    # 执行命令并捕获异常
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed on file {fname}.  Skipping. Error: {e}")
