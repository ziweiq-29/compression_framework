import csv
import subprocess
import glob
import os
import re
import shutil
import sys

PRESSIO = "/anvil/projects/x-cis240669/libpressio-env/.spack-env/view/bin/pressio"

# 通用参数
dims = "512 512 512"
datatype = "f"
mode = "REL"
# qcat_evaluators = "compareData,ssim,computeErrAutoCorrelation"
# qcat_evaluators = "ssim"
# qcat_evaluators = "compareData,ssim,computeErrAutoCorrelation"
error_bounds = ["1e-3", "5e-4", "1e-4", "5e-5", "1e-5", "5e-6", "1e-6","1e-1", "5e-2", "1e-2", "5e-3"]
# error_bounds = ["5e-4","5e-5"]
error_bounds_tthresh = [float(e) for e in error_bounds]
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# root_dir = "/anvil/projects/x-cis240669/EXAALT"  
# root_dir = "/anvil/projects/x-cis240669/NYX"  
# root_dir = "/anvil/projects/x-cis240669/LAMMPS-lj" 
root_dir = "/anvil/projects/x-cis240669/CESM" 
compressors = ["sperr","mgard","sz3","zfp"]
# compressors = ["sz3"]
output_root = os.path.join(_SCRIPT_DIR, "outputs", "DSSIM")
MAX_FILES = 500


def _parse_compressor_env(var_name, default):
    """Parse env var like 'mgard,sz3' or 'mgard sz3' into a compressor list."""
    raw = os.environ.get(var_name, "")
    if not raw or not raw.strip():
        return list(default)
    items = [x.strip() for x in re.split(r"[,\s]+", raw.strip()) if x.strip()]
    if not items:
        return list(default)
    # Keep user order while removing duplicates.
    return list(dict.fromkeys(items))


hedm_compressors = _parse_compressor_env("HEDM_COMPRESSORS", compressors)

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
standard_output_root = os.path.join(_SCRIPT_DIR, "outputs", "STANDARD")

# EXAALT（exxalt）与 LAMMPS-lj 两种根目录均可：prefixed（*.x.f32.dat + NxM）与 flat（x/y/z.f32.dat）自动识别
EXAALT_ROOT = "/anvil/projects/x-cis240669/EXAALT"
LAMMPS_LJ_ROOT = "/anvil/projects/x-cis240669/LAMMPS-lj"
# 任选一个，或 run_standard_exxalt([EXAALT_ROOT, LAMMPS_LJ_ROOT]) 一次跑两个
exxalt_root = LAMMPS_LJ_ROOT  # 改为 EXAALT_ROOT 即跑 exaalt 数据


def _short_metric_name(full_key):
    """去掉 'metric:' 前缀和 '<type>' 后缀，如 error_stat:psnr<double> -> psnr。"""
    name = full_key.split(":")[-1] if ":" in full_key else full_key
    if "<" in name:
        name = name.split("<")[0]
    return name


def _parse_pressio_metrics(text):
    """Parse pressio stdout: 'metric:name<type> = value' -> dict 短名 -> float or str。"""
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if " = " not in line:
            continue
        key_part, value_part = line.split(" = ", 1)
        key_part = key_part.strip()
        value_part = value_part.strip()
        short_key = _short_metric_name(key_part)
        try:
            v = float(value_part)
        except ValueError:
            v = value_part
        out[short_key] = v
    return out


def run_standard():
    """非 EXAALT：直接跑 pressio（不跑 main.py），-m error_stat -m ssim -M all，结果写 CSV。
    按输入文件分子目录，与 HALO 一致：outputs/STANDARD/<dataset_name>/<input_base>_<ext>/<compressor>_standard.csv
    """
    # EXAALT 布局时顶层只走了 is_exaalt 分支，未定义 _file_list / dataset_name；此处与顶层 else 一致
    dataset_name = os.path.basename(os.path.normpath(root_dir))
    # 遍历 root_dir 下所有 .dat（递归），只压缩这些文件
    dat_paths = sorted(glob.glob(os.path.join(root_dir, "**", "*.dat"), recursive=True))
    if MAX_FILES is not None:
        dat_paths = dat_paths[:MAX_FILES]
    print(f"[STANDARD] root_dir={root_dir} | {len(dat_paths)} .dat file(s)")

    # CSV 列名只用短名（无 metric: 前缀），如 mse, psnr, ssim
    base_metric_keys = [
        "compression_rate", "compression_rate_many", "decompression_rate", "decompression_rate_many",
        "average_difference", "average_error", "difference_range", "error_range",
        "max_error", "max_pw_rel_error", "max_rel_error",
        "min_error", "min_pw_rel_error", "min_rel_error",
        "mse", "n", "psnr", "rmse",
        "value_max", "value_mean", "value_min", "value_range", "value_std", "compression_ratio",
        "ssim",
    ]
    fieldnames = ["compressor name", "input", "error_bound"] + base_metric_keys

    def norm(v):
        try:
            return "{:.12g}".format(float(v))
        except Exception:
            return str(v).strip() if v is not None else ""

    for compressor in compressors:
        for input_path in dat_paths:
            fname = os.path.basename(input_path)
            if "log10" in fname:
                print(f"[SKIP] Skipping {fname} because it contains 'log10'")
                continue
            input_path = os.path.abspath(input_path)
            if not os.path.isfile(input_path):
                print(f"[SKIP] Not a file: {input_path}")
                continue
            input_basename = os.path.basename(fname)
            input_base, ext = os.path.splitext(fname)
            suffix = f"_{ext[1:].lower()}" if ext else ""
            var_dir = input_base + suffix
            output_dir = os.path.join(standard_output_root, dataset_name, var_dir)
            output_csv = os.path.join(output_dir, f"{compressor}_standard.csv")
            os.makedirs(output_dir, exist_ok=True)

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
                    pass
            index = {}
            for row in old_rows:
                comp = str(row.get("compressor name", "")).strip()
                inp = str(row.get("input", "")).strip()
                eb_val = norm(row.get("error_bound", ""))
                if comp and inp and eb_val:
                    index[(comp, inp, eb_val)] = row
            added, updated = 0, 0

            input_lower = input_path.lower()

            for eb in error_bounds:
                key = (compressor, input_basename, norm(eb))
                if key in index:
                    print(f"[STANDARD] skip existing {compressor} {input_basename} rel={eb}")
                    continue

                print(f"\n=== STANDARD {compressor} on {fname} | rel={eb} ===")
                # CESM 的 .dat 数据是 3600x1800，其它数据集默认用全局 dims（如 512x512x512）
                if dataset_name.lower() == "cesm":
                    dims_used = "3600 1800"
                else:
                    dims_used = dims
                cmd = [
                    PRESSIO,
                    "-i", input_path,
                    "-b", f"compressor={compressor}",
                    "-o", f"rel={eb}",
                    *[x for d in dims_used.split() for x in ("-d", d)],
                    "-t", "float",
                    "-b", "external:launch_metric=print",
                    "-m", "time",
                    "-m",  "size",
                    "-m", "error_stat",
                    "-m", "ssim",
                    "-M", "all",
                ]
                if input_lower.endswith(".h5") or input_lower.endswith(".hdf5"):
                    # -i 后必须紧跟文件路径，再插 -I；否则会变成 -i -I ... path 导致 pressio 找不到输入
                    cmd = cmd[:3] + ["-I", "/native_fields/baryon_density"] + cmd[3:]
                print("Command (pressio):", " ".join(cmd))
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
                if proc.returncode != 0:
                    print(f"[ERROR] pressio failed for {fname} rel={eb}", file=sys.stderr)
                    if proc.stderr:
                        print(proc.stderr[:2000], file=sys.stderr)
                    continue

                metrics = _parse_pressio_metrics(combined)
                row = {"compressor name": compressor, "input": input_basename, "error_bound": eb}
                for k, v in metrics.items():
                    if k not in fieldnames:
                        fieldnames.append(k)
                    row[k] = v

                if key in index:
                    for k, v in row.items():
                        if v is not None and v != "":
                            index[key][k] = v
                    updated += 1
                else:
                    full_row = {k: row.get(k, "") for k in fieldnames}
                    old_rows.append(full_row)
                    index[key] = full_row
                    added += 1

                # 每算完一个 datapoint 立即写回 CSV，避免中途被杀后重复计算
                with open(output_csv, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                    writer.writeheader()
                    for r in old_rows:
                        for k in fieldnames:
                            if k not in r:
                                r[k] = ""
                        writer.writerow(r)
                print(f"[STANDARD] {compressor} {fname} rel={eb}: written to {output_csv} | added={added}, updated={updated}")


def _collect_exxalt_xyz_jobs(input_root: str):
    """收集待压缩的三轴任务。两种布局：
    1) prefixed：prefix.x.f32.dat / .y / .z（如 p1/10x32000.x.f32.dat），dims 从 basename 的 NxM 解析。
    2) flat：目录下直接 x.f32.dat、y.f32.dat、z.f32.dat（如 p125/），dims 用文件字节数/4 一维。
    返回 [{"kind":"prefixed","prefix":...}, {"kind":"flat","dir":...}, ...]
    """
    input_root = os.path.abspath(input_root)
    jobs = []
    if not os.path.isdir(input_root):
        return jobs
    seen_flat = set()
    seen_prefixed = set()

    for dirpath, _dirnames, _filenames in os.walk(input_root):
        dirpath = os.path.abspath(dirpath)
        # flat：x.f32.dat / y.f32.dat / z.f32.dat 同名在目录根
        fx = os.path.join(dirpath, "x.f32.dat")
        fy = os.path.join(dirpath, "y.f32.dat")
        fz = os.path.join(dirpath, "z.f32.dat")
        if os.path.isfile(fx) and os.path.isfile(fy) and os.path.isfile(fz):
            if dirpath not in seen_flat:
                seen_flat.add(dirpath)
                jobs.append({"kind": "flat", "dir": dirpath})

        # prefixed：*.x.f32.dat 且同 prefix 有 .y/.z（排除已作为 flat 的 x.f32.dat）
        for p in sorted(glob.glob(os.path.join(dirpath, "*.x.f32.dat"))):
            if not p.endswith(".x.f32.dat"):
                continue
            if os.path.basename(p) == "x.f32.dat":
                continue  # 已由 flat 处理
            prefix = p[: -len(".x.f32.dat")]
            if os.path.isfile(prefix + ".y.f32.dat") and os.path.isfile(prefix + ".z.f32.dat"):
                prefix = os.path.abspath(prefix)
                if prefix not in seen_prefixed:
                    seen_prefixed.add(prefix)
                    jobs.append({"kind": "prefixed", "prefix": prefix})

    return jobs


def run_standard_exxalt(input_root=None):
    """对 exxalt/EXAALT 或 LAMMPS-lj 根目录跑 STANDARD pressio（x/y/z 分轴、同 cmd/CSV）。
    - input_root=None：使用全局 exxalt_root。
    - input_root 为 str：只跑该目录（设为 EXAALT_ROOT 或 LAMMPS_LJ_ROOT 均可）。
    - input_root 为 list/tuple：依次跑多个根目录，输出分别在 STANDARD/<basename>/...
    支持 prefixed（dataset1-5423x3137.x.f32.dat）与 flat（p125/x.f32.dat）；flat 用 size/4 一维。
    """
    if input_root is None:
        input_root = exxalt_root
    if isinstance(input_root, (list, tuple)):
        for r in input_root:
            run_standard_exxalt(r)
        return

    input_root = os.path.abspath(os.path.expanduser(str(input_root)))
    if not os.path.isdir(input_root):
        print(f"[STANDARD_EXXALT] skip: not a directory {input_root}")
        return
    jobs = _collect_exxalt_xyz_jobs(input_root)
    if MAX_FILES is not None:
        jobs = jobs[:MAX_FILES]
    if not jobs:
        print(f"[STANDARD_EXXALT] no x/y/z .f32.dat triplets under {input_root}")
        return
    dataset_name = os.path.basename(os.path.normpath(input_root))
    print(f"[STANDARD_EXXALT] root={input_root} | {len(jobs)} triplet group(s), each axis x/y/z compressed separately")

    base_metric_keys = [
        "compression_rate", "compression_rate_many", "decompression_rate", "decompression_rate_many",
        "average_difference", "average_error", "difference_range", "error_range",
        "max_error", "max_pw_rel_error", "max_rel_error",
        "min_error", "min_pw_rel_error", "min_rel_error",
        "mse", "n", "psnr", "rmse",
        "value_max", "value_mean", "value_min", "value_range", "value_std", "compression_ratio",
        "ssim",
    ]
    fieldnames = ["compressor name", "input", "error_bound"] + base_metric_keys

    def norm(v):
        try:
            return "{:.12g}".format(float(v))
        except Exception:
            return str(v).strip() if v is not None else ""

    axes = ("x", "y", "z")
    for compressor in compressors:
        for job in jobs:
            if job["kind"] == "prefixed":
                prefix_path = job["prefix"]
                dims_str = _exaalt_dims_from_prefix(prefix_path)
                if not dims_str:
                    print(f"[SKIP] {os.path.basename(prefix_path)}: cannot parse dims (expect *NxM in name)")
                    continue
                dim_list_shared = dims_str.split()
            else:
                prefix_path = None
                dim_list_shared = None  # per-file below

            for axis in axes:
                if job["kind"] == "prefixed":
                    input_path = prefix_path + "." + axis + ".f32.dat"
                else:
                    input_path = os.path.join(job["dir"], axis + ".f32.dat")
                if not os.path.isfile(input_path):
                    print(f"[SKIP] Not a file: {input_path}")
                    continue
                input_path = os.path.abspath(input_path)
                if job["kind"] == "flat":
                    try:
                        nfloats = os.path.getsize(input_path) // 4
                    except OSError:
                        nfloats = 0
                    if nfloats <= 0:
                        print(f"[SKIP] cannot infer dims for {input_path} (empty or unreadable)")
                        continue
                    dim_list = [str(nfloats)]
                else:
                    dim_list = dim_list_shared

                rel = os.path.relpath(input_path, input_root)
                # 按轴分目录
                if job["kind"] == "prefixed":
                    stem_rel = rel[: -len("." + axis + ".f32.dat")]
                else:
                    # flat：按目录 + 轴分子目录，如 p125_x_f32_dat
                    stem_rel = os.path.join(os.path.relpath(job["dir"], input_root), axis)
                var_dir = stem_rel.replace(os.sep, "_").replace(".", "_") + "_" + axis + "_f32_dat"
                input_basename = rel
                output_dir = os.path.join(standard_output_root, dataset_name, var_dir)
                output_csv = os.path.join(output_dir, f"{compressor}_standard.csv")
                os.makedirs(output_dir, exist_ok=True)

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
                        pass
                index = {}
                for row in old_rows:
                    comp = str(row.get("compressor name", "")).strip()
                    inp = str(row.get("input", "")).strip()
                    eb_val = norm(row.get("error_bound", ""))
                    if comp and inp and eb_val:
                        index[(comp, inp, eb_val)] = row
                added, updated = 0, 0
                input_lower = input_path.lower()

                for eb in error_bounds:
                    key = (compressor, input_basename, norm(eb))
                    if key in index:
                        print(f"[STANDARD_EXXALT] skip existing {compressor} {input_basename} rel={eb}")
                        continue

                    print(f"\n=== STANDARD_EXXALT {compressor} on {rel} | rel={eb} ===")
                    cmd = [
                        PRESSIO,
                        "-i", input_path,
                        "-b", f"compressor={compressor}",
                        "-o", f"rel={eb}",
                        *[x for d in dim_list for x in ("-d", d)],
                        "-t", "float",
                        "-b", "external:launch_metric=print",
                        "-m", "time",
                        "-m", "size",
                        "-m", "error_stat",
                        "-m", "ssim",
                        "-M", "all",
                    ]
                    if input_lower.endswith(".h5") or input_lower.endswith(".hdf5"):
                        cmd = cmd[:3] + ["-I", "/native_fields/baryon_density"] + cmd[3:]
                    print("Command (pressio):", " ".join(cmd))
                    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
                    if proc.returncode != 0:
                        print(f"[ERROR] pressio failed for {rel} rel={eb}", file=sys.stderr)
                        if proc.stderr:
                            print(proc.stderr[:2000], file=sys.stderr)
                        continue

                    metrics = _parse_pressio_metrics(combined)
                    row = {"compressor name": compressor, "input": input_basename, "error_bound": eb}
                    for k, v in metrics.items():
                        if k not in fieldnames:
                            fieldnames.append(k)
                        row[k] = v

                    if key in index:
                        for k, v in row.items():
                            if v is not None and v != "":
                                index[key][k] = v
                        updated += 1
                    else:
                        full_row = {k: row.get(k, "") for k in fieldnames}
                        old_rows.append(full_row)
                        index[key] = full_row
                        added += 1

                    # 每跑完一个 datapoint 立即写 CSV，中断重跑时无需重复计算
                    with open(output_csv, "w", newline="", encoding="utf-8") as f:
                        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                        writer.writeheader()
                        for r in old_rows:
                            for k in fieldnames:
                                if k not in r:
                                    r[k] = ""
                            writer.writerow(r)
                    print(f"[STANDARD_EXXALT] {compressor} {rel} rel={eb} -> {output_csv} | added={added}, updated={updated}")

                print(f"[STANDARD_EXXALT] {compressor} {rel}: done -> {output_csv} | total added={added}, updated={updated}")


# HEDM 固定输入与维度
# 先在 MIDAS 里将 ge5 payload 转成 float32 raw，再用该 raw 做压缩输入
HEDM_HEADER_SOURCE = "/anvil/projects/x-cis240669/midas/park_ss_ff_270MPa_000510.edf.ge5"
HEDM_INPUT = "/anvil/projects/x-cis240669/MIDAS/FF_HEDM/workflows/park_ss_ff_270MPa_000510.payload.float32.raw"
HEDM_DIMS = "1441 2048 2048"
hedm_output_root = os.path.join(_SCRIPT_DIR, "outputs", "HEDM")

# DSSIM: 遍历目录下所有 .dat，每个文件一个子目录保存（与 HALO/STANDARD 一致）
DSSIM_INPUT = "/anvil/projects/x-cis240669/CESM/"
DSSIM_DIMS = "3600 1800"  # 默认维度，可按需改为 per-file 映射
dssim_output_root = os.path.join(_SCRIPT_DIR, "outputs", "DSSIM")
dssim_dataset_name = os.path.basename(os.path.normpath(DSSIM_INPUT))  # e.g. CESM
DSSIM_REQUIRED_COLUMNS = [
    "compressor name", "input", "error_bound", "dssim",
    "mean", "min", "max", "median", "p90", "p99", "p999", "wasserstein_distance",
]


def _ensure_csv_columns(csv_path, required_columns):
    """Ensure CSV contains required columns; fill missing values with empty strings."""
    if not os.path.isfile(csv_path):
        return
    try:
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            old_fieldnames = list(reader.fieldnames or [])
            rows = list(reader)
    except Exception as e:
        print(f"[DSSIM] warn: cannot read CSV for column padding: {csv_path} ({e})")
        return

    fieldnames = list(old_fieldnames)
    changed = False
    for col in required_columns:
        if col not in fieldnames:
            fieldnames.append(col)
            changed = True
    if not changed:
        return

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            for col in fieldnames:
                if col not in row:
                    row[col] = ""
            writer.writerow(row)


def run_hedm():
    """HEDM: 读 float32 payload，跑 pressio+hedm_external，解析 [QOI] 写入 CSV。"""
    script = os.path.join(_SCRIPT_DIR, "run_hedm.py")
    if not os.path.isfile(script):
        print(f"[HEDM] skip: run_hedm.py not found at {script}")
        return
    if not os.path.isfile(HEDM_INPUT):
        print(f"[HEDM] skip: input not found {HEDM_INPUT}")
        return
    if not os.path.isfile(HEDM_HEADER_SOURCE):
        print(f"[HEDM] skip: header source not found {HEDM_HEADER_SOURCE}")
        return
    output_dir = os.path.abspath(hedm_output_root)
    print(f"[HEDM] compressors={hedm_compressors}")
    hedm_timeout = os.environ.get("HEDM_TIMEOUT_SEC", "1800").strip() or "1800"
    hedm_threads = os.environ.get("HEDM_EXTERNAL_THREADS", "1").strip() or "1"
    for compressor in hedm_compressors:
        print(f"\n=== HEDM float32 payload | {compressor} ===")
        for eb in error_bounds:
            # 每次只跑一个 datapoint（一个 error bound），确保该点完成后立即落盘到 CSV
            cmd = [
                "python", script,
                "--input", HEDM_INPUT,
                "--header-source", HEDM_HEADER_SOURCE,
                "--dims", *HEDM_DIMS.split(),
                "--error-bounds", eb,
                "--compressor", compressor,
                "--output-dir", output_dir,
                "--pressio-timeout-sec", hedm_timeout,
                "--external-num-threads", hedm_threads,
            ]
            if compressor == "sperr":
                # libpressio option is sperr:nthreads (not pressio:nthreads)
                cmd += ["--pressio-opts", "sperr:nthreads=5"]
            if compressor == "mgard":
                cmd += ["--pressio-opts", "mgard:dev_type_str=openmp"]
                cmd += ["--pressio-opts", "mgard:nthreads=5"]
            print("Command (hedm):", " ".join(cmd))
            try:
                subprocess.run(cmd, check=True, cwd=_SCRIPT_DIR)
            except subprocess.CalledProcessError as e:
                print(f"[ERROR] HEDM failed for {compressor} | rel={eb}.")
                print(e)


def run_dssim():
    """DSSIM: 遍历 DSSIM_INPUT 下所有 .dat，按变量前缀分组后逐组运行并写 CSV。"""
    script = os.path.join(_SCRIPT_DIR, "run_dssim.py")
    if not os.path.isfile(script):
        print(f"[DSSIM] skip: run_dssim.py not found at {script}")
        return
    input_root = os.path.abspath(DSSIM_INPUT)
    if not os.path.isdir(input_root):
        print(f"[DSSIM] skip: not a directory {DSSIM_INPUT}")
        return
    dat_files = sorted(glob.glob(os.path.join(input_root, "**", "*.dat")))
    if not dat_files:
        print(f"[DSSIM] skip: no .dat files under {DSSIM_INPUT}")
        return
    print(f"[DSSIM] root={input_root} | {len(dat_files)} .dat file(s)")
    grouped = {}
    for dat_path in dat_files:
        rel = os.path.relpath(dat_path, input_root)
        rel_no_ext = rel.replace(os.sep, "_").rsplit(".", 1)[0]  # e.g. CLDHGH_CLDHGH_04
        # Use the first token in filename stem as group prefix:
        # CLDHGH_04.dat -> CLDHGH
        # CLDHGH_CLDHGH_04.dat -> CLDHGH
        stem = os.path.splitext(os.path.basename(dat_path))[0]
        prefix = stem.split("_", 1)[0] if "_" in stem else stem
        grouped.setdefault(prefix, []).append((dat_path, rel, rel_no_ext))

    for prefix in sorted(grouped):
        items = sorted(grouped[prefix], key=lambda x: x[1])
        print(f"\n[DSSIM] Prefix group: {prefix} | {len(items)} file(s)")
        for dat_path, rel, rel_no_ext in items:
            # Keep per-file folder under each prefix:
            # .../CESM/CLDHGH_CLDHGH/CLDHGH_CLDHGH_04_dat
            var_dir = rel_no_ext + "_dat"
            output_dir = os.path.join(dssim_output_root, dssim_dataset_name, prefix, var_dir)
            for compressor in compressors:
                print(f"\n=== DSSIM {compressor} | {rel} | group={prefix} ===")
                output_csv = os.path.join(os.path.abspath(output_dir), f"{compressor}_dssim.csv")
                for eb in error_bounds:
                    cmd = [
                        "python", script,
                        "--input", os.path.abspath(dat_path),
                        "--dims", *DSSIM_DIMS.split(),
                        "--error-bounds", eb,
                        "--compressor", compressor,
                        "--output-dir", os.path.abspath(output_dir),
                    ]
                    print("Command (dssim):", " ".join(cmd))
                    try:
                        subprocess.run(cmd, check=True, cwd=_SCRIPT_DIR)
                        _ensure_csv_columns(output_csv, DSSIM_REQUIRED_COLUMNS)
                    except subprocess.CalledProcessError as e:
                        print(f"[ERROR] DSSIM failed for {compressor} | {rel} | rel={eb}")
                        print(e)


# if is_exaalt:
#     run_exaalt()
# else:
#     run_halo()
    # run_standard()
run_hedm()
# run_standard()
# run_dssim()
# run_halo()
# run_exaalt()
# 只跑当前 exxalt_root：
# run_standard_exxalt()
# 两个根都跑（EXAALT + LAMMPS-lj）：
# run_standard_exxalt([EXAALT_ROOT, LAMMPS_LJ_ROOT])