import subprocess
import glob
import os
import re
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
error_bounds = ["1e-3", "5e-4"]
error_bounds_tthresh = [float(e) for e in error_bounds]
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
root_dir = "/anvil/projects/x-cis240669/EXAALT"  
# root_dir = "/anvil/projects/x-cis240669/NYX"  
# root_dir = "/anvil/projects/x-cis240669/LAMMPS-lj" 
compressors = ["sz3"]
output_root = os.path.join(_SCRIPT_DIR, "outputs", "RDF")
MAX_FILES = 2

# 按结构检测：子目录下存在 .x/.y/.z.f32.dat 成对则用 RDF(EXAALT-style)，否则用 STANDARD
_exaalt_datasets = []  # [(dataset_dir, dataset_name, [prefix, ...]), ...]
if os.path.isdir(root_dir):
    for name in sorted(os.listdir(root_dir)):
        dataset_dir = os.path.join(root_dir, name)
        if not os.path.isdir(dataset_dir):
            continue
        # 只匹配 .x.f32.dat（不匹配 .x.f32.dat.ts0 等）
        x_files = sorted(glob.glob(os.path.join(dataset_dir, "*.x.f32.dat")))
        prefix_list = []
        for p in x_files:
            if not p.endswith(".x.f32.dat"):
                continue
            prefix = p[: -len(".x.f32.dat")]
            if os.path.isfile(prefix + ".y.f32.dat") and os.path.isfile(prefix + ".z.f32.dat"):
                prefix_list.append(prefix)
        if MAX_FILES is not None:
            prefix_list = prefix_list[:MAX_FILES]
        if prefix_list:
            _exaalt_datasets.append((dataset_dir, name, prefix_list))
is_exaalt = len(_exaalt_datasets) > 0
if is_exaalt:
    print(f"[RDF/EXAALT-style] root={root_dir} | {len(_exaalt_datasets)} dataset(s): {[d[1] for d in _exaalt_datasets]}")
else:
    dataset_name = os.path.basename(os.path.normpath(root_dir))
    _file_list = sorted(os.listdir(root_dir))
    if MAX_FILES is not None:
        _file_list = _file_list[:MAX_FILES]
    print(f"[STANDARD] root_dir={root_dir} | {len(_file_list)} file(s)")


def _exaalt_dims_from_prefix(prefix_path: str):
    """从 prefix 的 basename 解析 nt na。支持 dataset1-7852x1037、10x32000 等 *NxM 格式 -> "7852 1037" / "10 32000"。无法解析则返回 None。"""
    base = os.path.basename(prefix_path)
    m = re.search(r"(\d+)x(\d+)$", base)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return None


def run_exaalt():
    """EXAALT: 遍历每个子目录（dataset），再遍历其下每个 prefix，跑 main + run_rdf_pressio；维度从文件名解析。"""
    for dataset_dir, dataset_name, prefix_list in _exaalt_datasets:
        print(f"\n=== EXAALT dataset: {dataset_name} ===")
        for prefix_path in prefix_list:
            input_base = os.path.basename(prefix_path)
            prefix_dims = _exaalt_dims_from_prefix(prefix_path)
            if not prefix_dims:
                print(f"[SKIP] {input_base}: cannot parse dims from name (expect *-NxM)")
                continue
            var_dir = input_base + "_f32"
            output_dir = os.path.abspath(os.path.join(output_root, dataset_name, var_dir))
            input_x = prefix_path + ".x.f32.dat"
            print(f"\n--- prefix: {input_base} (dims={prefix_dims}) ---")
            for compressor in compressors:
                print(f"  {compressor} ...")
                for f in glob.glob(os.path.join(_SCRIPT_DIR, "tmp_*.compressed")) + glob.glob(os.path.join(_SCRIPT_DIR, "tmp_*.out")):
                    try:
                        os.remove(f)
                    except OSError:
                        pass
                run_rdf_script = os.path.join(_SCRIPT_DIR, "run_rdf_pressio.py")
                cmd_rdf = [
                    "python", run_rdf_script,
                    "--input", os.path.abspath(prefix_path),
                    "--dims", *prefix_dims.split(),
                    "--error-bounds", *error_bounds,
                    "--compressor", compressor,
                    "--output-dir", output_dir,
                ]
                if compressor == "sz3":
                    cmd_rdf += ["--pressio-opts", "sz3:algorithm_str=ALGO_BIOMD"]
                try:
                    print("Command (rdf):", " ".join(cmd_rdf))
                    subprocess.run(cmd_rdf, check=True, cwd=_SCRIPT_DIR)
                except subprocess.CalledProcessError as e:
                    print(f"[ERROR] Failed on {input_base} / {compressor}. Skipping.")
                    print(e)
def run_halo():
        for fname in _file_list:
            if "log10" in fname:
                print(f"[SKIP] Skipping {fname} because it contains 'log10'")
                continue
            for compressor in compressors:
                input_path = os.path.join(root_dir, fname)
                print(f"\n=== Running {compressor} on {fname} ===")
                input_base, ext = os.path.splitext(fname)
                suffix = f"_{ext[1:].lower()}" if ext else ""
                var_dir = input_base + suffix
                output_dir = os.path.join(output_root, dataset_name, var_dir)
                for f in glob.glob("tmp_*.compressed") + glob.glob("tmp_*.out"):
                    os.remove(f)
                cmd_halo = [
                    "python", "run_halo_pressio.py",
                    "--input", input_path,
                    "--dims", *dims.split(),
                    "--error-bounds", *error_bounds,
                    "--compressor", compressor,
                    "--datatype", datatype,
                    "--output-dir", output_dir,
                ]
                try:
                    print("Command (halo):", " ".join(cmd_halo))
                    subprocess.run(cmd_halo, check=True)
                except subprocess.CalledProcessError as e:
                    print(f"[ERROR] Failed on {fname}. Skipping.")
                    print(e)
def run_standard():
    """非 EXAALT：按单文件跑 main + halo（或仅 halo）"""
    for fname in _file_list:
        if "log10" in fname:
            print(f"[SKIP] Skipping {fname} because it contains 'log10'")
            continue
        for compressor in compressors:
            input_path = os.path.join(root_dir, fname)
            print(f"\n=== Running {compressor} on {fname} ===")
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
            try:
                print("Command (main):", " ".join(cmd))
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as e:
                print(f"[ERROR] Failed on {fname}. Skipping.")
                print(e)


if is_exaalt:
    run_exaalt()
else:
    run_halo()
    # run_standard()
