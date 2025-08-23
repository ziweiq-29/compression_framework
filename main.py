import yaml
import argparse
import pandas as pd
from runner import run_pipeline
import config_registry
import os
import subprocess
from qcat_runner import run_evaluators
import csv
import uuid
unique_id = str(uuid.uuid4())[:8] 
import hashlib
import glob

parser = argparse.ArgumentParser()
parser.add_argument("--compressor", required=True, choices=["sz3", "qoz","sperr3d","sperr2d","zfp","tthresh","faz","mgard"])
parser.add_argument("--mode",type=str, choices=["ABS", "REL","PSNR","NORM","RATE","LOSELESS"])
parser.add_argument("--value", type=str, help="Single error bound value")
parser.add_argument("--sweep", nargs="*", help="Sweep a list of error bounds")
parser.add_argument("--level", type=int, help="zstd compression level")
parser.add_argument("--dims", type=str, required=True, help="e.g. '512 512 512'")
parser.add_argument("--input", required=True)
parser.add_argument("--enable-qcat", action="store_true", help="Enable qcat evaluation")
parser.add_argument("--enable-calc_stats", action="store_true", help="Enable calcErrStats.py evaluation")
parser.add_argument("--block-size", type=int, default=-1, help="Block size for calcErrStats.py, default is -1 (global stats)")
parser.add_argument("--shift-size", type=int, help="Shift size for calcErrStats.py, required if block-size > 0")
parser.add_argument("--output-prefix", type=str, help="Output prefix for calcErrStats.py, required if block-size > 0")
parser.add_argument("--datatype", choices=["f", "d"], required=True, help="Data type (f for float, d for double)")
parser.add_argument('--smooth', type=float, help='Smooth parameter (only used for MGARD)')
parser.add_argument("--qcat-evaluators", type=str, default="ssim,compareData",
                    help="Comma-separated list of qcat evaluators to use (default: 'ssim,compareData')")
parser.add_argument("--lossless", type=str, default="huffman-zstd", choices=["huffman", "huffman-lz4", "huffman-zstd"], help="MGARD lossless backend")
parser.add_argument("--verbose", type=str, default="2", choices=["0", "1", "2", "3"], help="MGARD verbose level")
parser.add_argument(
    "-T", "--tunning_target",
    type=str,
    default=None,      # 默认为 None，也就是不加 -T
    help="Optional tunning target type (e.g., AC, PSNR)"
)

args = parser.parse_args()




compressed_file = "tmp_compressed"
args.input = os.path.abspath(args.input)
input_file_name = os.path.basename(args.input)
# print("args input is:///////", args.input)
# print("Extracted input file name:", input_file_name)
decompressed_file = os.path.abspath("tmp_decompressed.sz.out")

with open("configs/compressor_templates.yaml") as f:
    compressor_templates = yaml.safe_load(f)["compressors"]
    
    

# for f in glob.glob("tmp_*.compressed") + glob.glob("tmp_*.out"):
#     os.remove(f)
  
def run_calc_err_stats(datatype, ori_file, dec_file, dims, block_size, shift_size=None, output_prefix=None):
    # 构造 calcErrStats.py 命令
    cmd = [
        "python",
        os.path.abspath("calcErrStats.py"),
        "float" if datatype == "-f" else "double",
        ori_file,
        dec_file,
        str(len(dims))
    ] + [str(dim) for dim in dims]

    # 全局统计
    if block_size < 0:
        cmd += [str(block_size)]
    # 分块统计
    else:
        cmd += [str(block_size), str(shift_size), output_prefix]
    # print("calc_stat_cmd is: ", cmd)
    print("[DEBUG] Running calcErrStats.py:", " ".join(cmd))

    # 执行命令
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print("[ERROR] Failed to run calcErrStats.py")
        print(e.stderr)
results = []
name=""




def append_result_to_csv(results):
    if results:
        merge_key = "error_bound"
        results_csv_path = os.path.join(output_dir, name + "_results.csv")
        results = list(results)

        # 读取旧数据
        old_header, old_rows = [], []
        if os.path.exists(results_csv_path):
            with open(results_csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                old_header = reader.fieldnames or []
                old_rows = list(reader)

        # 数值标准化，避免 1e-1 != 0.1
        def norm(v):
            try:
                return "{:.12g}".format(float(v))
            except Exception:
                return str(v).strip()

        # 用 error_bound 建索引
        index = {}
        if merge_key in old_header:
            for row in old_rows:
                key_val = norm(row.get(merge_key, ""))
                if key_val:
                    index[key_val] = row

        # 合并表头
        new_keys_from_results = {k for r in results for k in r.keys()}
        all_keys = list(old_header) if old_header else []
        for k in new_keys_from_results:
            if k not in all_keys:
                all_keys.append(k)

        added_rows = 0
        updated_rows = 0

        for r in results:
            key_val = norm(r.get(merge_key, "")) if merge_key in r else None
            if key_val and key_val in index:
                # 行已存在 → 只补空值
                target = index[key_val]
                for k, v in r.items():
                    if str(target.get(k, "")).strip() == "" and v is not None:
                        target[k] = v
                updated_rows += 1
            else:
                # 新行
                new_row = {k: r.get(k, "") for k in all_keys}
                old_rows.append(new_row)
                if key_val:
                    index[key_val] = new_row
                added_rows += 1

    # 写回
        with open(results_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
            writer.writeheader()
            for row in old_rows:
                for k in all_keys:
                    if k not in row:
                        row[k] = ""
                writer.writerow(row)

            print(f"[INFO] Results merged to: {results_csv_path} | updated={updated_rows}, added={added_rows}")
    else:
        print("[WARN] No results to write.")
    














if args.compressor == "sz3":
    output_root = "outputs"
    input_path = args.input  # e.g. dataset/NYX/baryon_density.f32

    dataset_name = os.path.basename(os.path.dirname(input_path))      # NYX
    input_base, ext = os.path.splitext(os.path.basename(input_path))  # ("baryon_density", ".f32")

 
    suffix = f"_{ext[1:].lower()}" if ext else ""

    output_dir = os.path.join(output_root, dataset_name, f"{input_base}{suffix}")
    
    os.makedirs(output_dir, exist_ok=True)
    name = "sz3"
    dim_list = args.dims.strip().split()
    dims_flag = f"-{len(dim_list)}"            # 例如：-2, -3
    dims_values = " ".join(dim_list)  
    sz3_templates = compressor_templates["sz3"]
    for cfg in config_registry.get_sz3_configs(args):
        # print("[DEBUG] Compress cfg:", cfg)
        compressed_file = os.path.abspath(f"tmp_{cfg['error_bound']}.compressed")
        decompressed_file = os.path.abspath(f"tmp_{cfg['error_bound']}.sz.out")
        compress_cmd = sz3_templates["compress_template"].format(
            input=args.input,
            compressed=compressed_file,
            decompressed=decompressed_file,
            dims=dims_flag,
            dimsList=dims_values,
            mode=cfg["mode"],
            arg=cfg["arg"],
            datatype=cfg["datatype"]
        )

        print(f"[DEBUG] Running compress: {compress_cmd}")
        # print(f"[DEBUG] Running decompress: {decompress_cmd}")
        
        result={}
        result["compressor name"] = "sz3"
        result_metrics={}
        
        result_metrics = run_pipeline(
            cfg["name"], 
            {
                "compress_cmd": compress_cmd,
            }, 
            args.input, 
            compressed_file,
            parser = "sz3"
        )
        
        if args.enable_calc_stats:

            run_calc_err_stats(
                datatype=cfg["datatype"],
                ori_file=args.input,
                dec_file=decompressed_file,
                dims=[int(d) for d in args.dims.split()],
                block_size=args.block_size,
                shift_size=args.shift_size,
                output_prefix=args.output_prefix
            )     

        
        dtype_map = {
    "-f": "single precision",
    "-d": "double precision"
}
        
        result["input_file"] = input_file_name
        result["data_type"] = dtype_map.get(cfg["datatype"])
        result["compression_ratio"] = result_metrics["compression_ratio"]
        result["compress_time(s)"] = result_metrics["compress_time"]
        result["mode"] = cfg["mode"]
        result["error_bound"] = cfg["error_bound"]
        result["decompress_time(s)"] = result_metrics["decompress_time"]
        result["ori_size(B)"] = result_metrics["size_of_file"]
        

        if args.enable_qcat:
            qcat_results = {}
            qcat_templates = compressor_templates["qcat"]["evaluators"]
            evaluator_keys = args.qcat_evaluators.split(",")
            qcat_results = run_evaluators(
                evaluator_templates=qcat_templates,
                evaluator_keys=evaluator_keys,  # 或根据 args 参数决定哪些分析器
                datatype=args.datatype,
                input=args.input,
                decompressed=decompressed_file,
                dims=args.dims
            )
            print(f"[DEBUG] qcat_results: {qcat_results}")
            result.update(qcat_results)
        results.append(result)   
    
    
        append_result_to_csv(results)

        
        
        
        
        
        
elif args.compressor == "qoz":
    
    output_root = "outputs"
    input_path = args.input  

    dataset_name = os.path.basename(os.path.dirname(input_path))      
    input_base, ext = os.path.splitext(os.path.basename(input_path)) 

   
    suffix = f"_{ext[1:].lower()}" if ext else ""

    # output_dir = os.path.join(output_root, dataset_name, f"{input_base}{suffix}")
    if args.tunning_target == "AC":
        output_dir = os.path.join(output_root, dataset_name, "AC", f"{input_base}{suffix}")
    else:
        output_dir = os.path.join(output_root, dataset_name, f"{input_base}{suffix}")

    
    os.makedirs(output_dir, exist_ok=True)
    name = "qoz"
    qoz_templates = compressor_templates["qoz"]
    dim_list = args.dims.strip().split()
    dims_flag = f"-{len(dim_list)}"            # 例如：-2, -3
    dims_values = " ".join(dim_list)  
    for cfg in config_registry.get_QoZ_configs(args):
        compressed_file = os.path.abspath(f"tmp_{cfg['error_bound']}.compressed")
        decompressed_file = os.path.abspath(f"tmp_{cfg['error_bound']}.qoz.out")
        
        compress_cmd = qoz_templates["compress_template"].format(
            input=args.input,
            compressed=compressed_file,
            decompressed=decompressed_file,
            dims=dims_flag,
            dimsList=dims_values,
            mode=cfg["mode"],
            arg=cfg["arg"],
            datatype=cfg["datatype"],
            tunning_target_flag=cfg["tunning_target_flag"]
        )
        print(f"[DEBUG] Running compress: {compress_cmd}")
        result={}
        result["compressor name"] = "qoz"
        result_metrics = {}

        
        result_metrics = run_pipeline(
            cfg["name"], 
            {
                "compress_cmd": compress_cmd,
            }, 
            args.input, 
            compressed_file,
            parser = "sz3"
        )
        
        if args.enable_calc_stats:
            run_calc_err_stats(
                datatype=cfg["datatype"],
                ori_file=args.input,
                dec_file=decompressed_file,
                dims=[int(d) for d in args.dims.split()],
                block_size=args.block_size,
                shift_size=args.shift_size,
                output_prefix=args.output_prefix
            )
        dtype_map = {
        "-f": "single precision",
        "-d": "double precision"
    }
        result["input_file(B)"] = input_file_name
        result["data_type"] = dtype_map.get(cfg["datatype"])
        result["compression_ratio"] = result_metrics["compression_ratio"]
        result["compress_time(s)"] = result_metrics["compress_time"]
        result["mode"] = cfg["mode"]
        result["error_bound"] = cfg["error_bound"]
        result["decompress_time(s)"] = result_metrics["decompress_time"]
        result["ori_size(B)"] = result_metrics["size_of_file"]
        
        
        if args.enable_qcat:
            qcat_results = {}
            qcat_templates = compressor_templates["qcat"]["evaluators"]
            evaluator_keys = args.qcat_evaluators.split(",")
            qcat_results = run_evaluators(
                evaluator_templates=qcat_templates,
                evaluator_keys=evaluator_keys,  
                datatype=args.datatype,
                input=args.input,
                decompressed=decompressed_file,
                dims=args.dims
            )
            result.update(qcat_results)
        results.append(result)

    
    
    
        append_result_to_csv(results)
    
elif args.compressor == "sperr3d":
    output_root = "outputs"
    input_path = args.input  

    dataset_name = os.path.basename(os.path.dirname(input_path))      
    input_base, ext = os.path.splitext(os.path.basename(input_path)) 

   
    suffix = f"_{ext[1:].lower()}" if ext else ""

    output_dir = os.path.join(output_root, dataset_name, f"{input_base}{suffix}")

    
    os.makedirs(output_dir, exist_ok=True)
    name = "sperr3d"
    configs = config_registry.get_sperr_configs(args)
    print(f"[DEBUG] sperr config count: {len(configs)}")
    sperr_templates = compressor_templates["sperr3d"]
    for cfg in config_registry.get_sperr_configs(args):
        compressed_file = os.path.abspath(f"tmp_{cfg['error_bound']}.sperr")
        decompressed_file = os.path.abspath(f"tmp_{cfg['error_bound']}.sperr.out")
        
        # 构造压缩和解压命令
        compress_cmd = sperr_templates["compress_template"].format(
            input=args.input,
            decompressed=decompressed_file,
            compressed=compressed_file,
            dims=args.dims,
            mode=cfg["mode"],
            arg=cfg["arg"],
            ftype=cfg["datatype"]
        )
        print(f"[DEBUG] Running compress: {compress_cmd}")
        
        result = {}
        result["compressor name"] = "sperr3d"
        result_metrics = run_pipeline(
            # cfg["name"], 
            name,
            {
                "compress_cmd": compress_cmd,
            }, 
            args.input, 
            compressed_file,
            parser = "sperr3d"
        )
        dtype_map = {
            "32": "single precision",
            "64": "double precision"
        }
        # 如果启用了 calcErrStats
        if args.enable_calc_stats:
            dtype="-f" if args.datatype == "f" else "-d"
            run_calc_err_stats(
                datatype=dtype,
                ori_file=args.input,
                dec_file=decompressed_file,
                dims=[int(d) for d in args.dims.split()],
                block_size=args.block_size,
                shift_size=args.shift_size,
                output_prefix=args.output_prefix
            )


        
        result["input_file(B)"] = input_file_name
        result["data_type"] = dtype_map.get(cfg["datatype"])
        result["compression_ratio"] = result_metrics["compression_ratio"]
        result["compress_time(s)"] = result_metrics["compress_time"]
        result["mode"] = cfg["mode"]
        result["error_bound"] = cfg["error_bound"]
        result["decompress_time(s)"] = result_metrics["decompress_time"]
        result["ori_size(B)"] = result_metrics["size_of_file"]
        
        # 如果启用了 qcat
        if args.enable_qcat:
            qcat_results = {}
            qcat_templates = compressor_templates["qcat"]["evaluators"]
            evaluator_keys = args.qcat_evaluators.split(",")
            qcat_results = run_evaluators(
                evaluator_templates=qcat_templates,
                evaluator_keys=evaluator_keys,
                datatype=args.datatype,
                input=args.input,
                decompressed=decompressed_file,
                dims=args.dims
            )
            result.update(qcat_results)
        results.append(result)

    
        append_result_to_csv(results)
        


elif args.compressor == "sperr2d":
    output_root = "outputs"
    input_path = args.input  

    dataset_name = os.path.basename(os.path.dirname(input_path))      
    input_base, ext = os.path.splitext(os.path.basename(input_path)) 

   
    suffix = f"_{ext[1:].lower()}" if ext else ""

    output_dir = os.path.join(output_root, dataset_name, f"{input_base}{suffix}")
    
    os.makedirs(output_dir, exist_ok=True)
    name = "sperr2d"
    configs = config_registry.get_sperr_configs(args)
    print(f"[DEBUG] sperr config count: {len(configs)}")
    sperr_templates = compressor_templates["sperr2d"]
    for cfg in config_registry.get_sperr_configs(args):
        compressed_file = os.path.abspath(f"tmp_{cfg['error_bound']}.sperr")
        decompressed_file = os.path.abspath(f"tmp_{cfg['error_bound']}.sperr.out")
        
        # 构造压缩和解压命令
        compress_cmd = sperr_templates["compress_template"].format(
            input=args.input,
            decompressed=decompressed_file,
            compressed=compressed_file,
            dims=args.dims,
            mode=cfg["mode"],
            arg=cfg["arg"],
            ftype=cfg["datatype"]
        )
        print(f"[DEBUG] Running compress: {compress_cmd}")
        
        result = {}
        result["compressor name"] = "sperr2d"
        result_metrics = run_pipeline(
            name,
            # cfg["name"], 
            {
                "compress_cmd": compress_cmd,
            }, 
            args.input, 
            compressed_file,
            parser = "sperr3d"
        )
        dtype_map = {
            "32": "single precision",
            "64": "double precision"
        }
        # 如果启用了 calcErrStats
        if args.enable_calc_stats:
            dtype="-f" if args.datatype == "f" else "-d"
            run_calc_err_stats(
                datatype=dtype,
                ori_file=args.input,
                dec_file=decompressed_file,
                dims=[int(d) for d in args.dims.split()],
                block_size=args.block_size,
                shift_size=args.shift_size,
                output_prefix=args.output_prefix
            )


        
        result["input_file(B)"] = input_file_name
        result["data_type"] = dtype_map.get(cfg["datatype"])
        result["compression_ratio"] = result_metrics["compression_ratio"]
        result["compress_time(s)"] = result_metrics["compress_time"]
        result["mode"] = cfg["mode"]
        result["error_bound"] = cfg["error_bound"]
        result["decompress_time(s)"] = result_metrics["decompress_time"]
        result["ori_size(B)"] = result_metrics["size_of_file"]
        
        # 如果启用了 qcat
        if args.enable_qcat:
            qcat_results = {}
            qcat_templates = compressor_templates["qcat"]["evaluators"]
            evaluator_keys = args.qcat_evaluators.split(",")
            qcat_results = run_evaluators(
                evaluator_templates=qcat_templates,
                evaluator_keys=evaluator_keys,
                datatype=args.datatype,
                input=args.input,
                decompressed=decompressed_file,
                dims=args.dims
            )
            result.update(qcat_results)
        results.append(result)
        
        
    
        append_result_to_csv(results)








elif args.compressor == "zfp":
    output_root = "outputs"
    input_path = args.input  

    dataset_name = os.path.basename(os.path.dirname(input_path))      
    input_base, ext = os.path.splitext(os.path.basename(input_path)) 

   
    suffix = f"_{ext[1:].lower()}" if ext else ""

    output_dir = os.path.join(output_root, dataset_name, f"{input_base}{suffix}")
    
    os.makedirs(output_dir, exist_ok=True)
    name = "zfp"
    dim_list = args.dims.strip().split()
    dims_flag = f"-{len(dim_list)}"            # 例如：-2, -3
    dims_values = " ".join(dim_list)  
    sz3_templates = compressor_templates["zfp"]
    for cfg in config_registry.get_zfp_configs(args):
        # print("[DEBUG] Compress cfg:", cfg)
        compressed_file = os.path.abspath(f"tmp_{cfg['error_bound']}.compressed")
        decompressed_file = os.path.abspath(f"tmp_{cfg['error_bound']}.zfp.out")
        compress_cmd = sz3_templates["compress_template"].format(
            input=args.input,
            compressed=compressed_file,
            decompressed=decompressed_file,
            dims=dims_flag,
            dimsList=dims_values,
            mode=cfg["mode"],
            arg=cfg["arg"],
            datatype=cfg["datatype"]
        )

        print(f"[DEBUG] Running compress: {compress_cmd}")
        # print(f"[DEBUG] Running decompress: {decompress_cmd}")
        
        result={}
        result["compressor name"] = "zfp"
        result_metrics={}
        
        result_metrics = run_pipeline(
            cfg["name"], 
            {
                "compress_cmd": compress_cmd,
            }, 
            args.input, 
            compressed_file,
            parser = "zfp"
        )
        
        if args.enable_calc_stats:
            dtype="-f" if args.datatype == "f" else "-d"
            run_calc_err_stats(
                datatype=dtype,
                ori_file=args.input,
                dec_file=decompressed_file,
                dims=[int(d) for d in args.dims.split()],
                block_size=args.block_size,
                shift_size=args.shift_size,
                output_prefix=args.output_prefix
            )     

        
        dtype_map = {
    "-f": "single precision",
    "-d": "double precision"
}
        
        result["input_file(B)"] = input_file_name
        result["data_type"] = dtype_map.get(cfg["datatype"])
        result["compression_ratio"] = result_metrics["compression_ratio"]
        result["compress_time(s)"] = result_metrics["compress_time"]
        # result["mode"] = cfg["mode"]
        result["mode"] = args.mode
        result["error_bound"] = cfg["error_bound"]
        result["decompress_time(s)"] = result_metrics["decompress_time"]
        result["ori_size(B)"] = result_metrics["size_of_file"]
        

        if args.enable_qcat:
            qcat_results = {}
            qcat_templates = compressor_templates["qcat"]["evaluators"]
            evaluator_keys = args.qcat_evaluators.split(",")
            qcat_results = run_evaluators(
                evaluator_templates=qcat_templates,
                evaluator_keys=evaluator_keys,  # 或根据 args 参数决定哪些分析器
                datatype=args.datatype,
                input=args.input,
                decompressed=decompressed_file,
                dims=args.dims
            )
            print(f"[DEBUG] qcat_results: {qcat_results}")
            result.update(qcat_results)
        results.append(result)   
        
        
    
        append_result_to_csv(results)


elif args.compressor == "tthresh":
    output_root = "outputs"
    input_path = args.input  

    dataset_name = os.path.basename(os.path.dirname(input_path))      
    input_base, ext = os.path.splitext(os.path.basename(input_path)) 

   
    suffix = f"_{ext[1:].lower()}" if ext else ""

    output_dir = os.path.join(output_root, dataset_name, f"{input_base}{suffix}")
    
    os.makedirs(output_dir, exist_ok=True)
    
    name = "tthresh"
    dim_list = args.dims.strip().split()
    dims_values = " ".join(dim_list)
    templates = compressor_templates["tthresh"]
    for cfg in config_registry.get_tthresh_configs(args):
        compressed_file = os.path.abspath(f"tmp_{cfg['error_bound']}.compressed")
        decompressed_file = os.path.abspath(f"tmp_{cfg['error_bound']}.tthresh.out")

        compress_cmd = templates["compress_template"].format(
            input=args.input,
            compressed=compressed_file,
            decompressed=decompressed_file,
            dimsList=dims_values,
            mode=cfg["mode"],
            arg=cfg["arg"],
            datatype=cfg["datatype"]
        )

        print(f"[DEBUG] Running compress: {compress_cmd}")
        result = {}
        result["compressor name"] = "tthresh"

        result_metrics = run_pipeline(
            cfg["name"],
            {
                "compress_cmd": compress_cmd,
            },
            args.input,
            compressed_file,
            parser="tthresh"
        )

        # 添加基本信息
        dtype_map = {
            "float": "single precision",
            "double": "double precision"
        }

        result["input_file"] = input_file_name
        result["data_type"] = dtype_map.get(cfg["datatype"])
        result["compression_ratio"] = result_metrics["compression_ratio"]
        result["compress_time(s)"] = result_metrics["compress_time"]
        result["decompress_time(s)"] = result_metrics["decompress_time"]
        

        result["mode"] = args.mode
        print(f"[DEBUG] args.mode = {args.mode}, type = {type(args.mode)}")
        result["error_bound"] = cfg["error_bound"]
        result["ori_size(B)"] = result_metrics["size_of_file"]

        if args.enable_qcat:
            qcat_templates = compressor_templates["qcat"]["evaluators"]
            evaluator_keys = args.qcat_evaluators.split(",")
            qcat_results = run_evaluators(
                evaluator_templates=qcat_templates,
                evaluator_keys=evaluator_keys,
                datatype=args.datatype,
                input=args.input,
                decompressed=decompressed_file,
                dims=args.dims
            )
            print(f"[DEBUG] qcat_results: {qcat_results}")
            result.update(qcat_results)

        
            if args.enable_calc_stats:
                dtype="-f" if args.datatype == "f" else "-d"
                run_calc_err_stats(
                    datatype=dtype,
                    ori_file=args.input,
                    dec_file=decompressed_file,
                    dims=[int(d) for d in args.dims.split()],
                    block_size=args.block_size,
                    shift_size=args.shift_size,
                    output_prefix=args.output_prefix
                )     
        
        
        results.append(result)
        
        
        
        
    
        append_result_to_csv(results)
        
elif args.compressor == "faz":
    output_root = "outputs"
    input_path = args.input  

    dataset_name = os.path.basename(os.path.dirname(input_path))      
    input_base, ext = os.path.splitext(os.path.basename(input_path)) 

   
    suffix = f"_{ext[1:].lower()}" if ext else ""

    # output_dir = os.path.join(output_root, dataset_name, f"{input_base}{suffix}")
    if args.tunning_target == "AC":
        output_dir = os.path.join(output_root, dataset_name, "AC", f"{input_base}{suffix}")
    else:
        output_dir = os.path.join(output_root, dataset_name, f"{input_base}{suffix}")
    
    os.makedirs(output_dir, exist_ok=True)
    
    name = "faz"
    dim_list = args.dims.strip().split()
    dims_flag = f"-{len(dim_list)}"            # 例如：-2, -3
    dims_values = " ".join(dim_list)  
    sz3_templates = compressor_templates["faz"]
    for cfg in config_registry.get_faz_configs(args):
        # print("[DEBUG] Compress cfg:", cfg)
        compressed_file = os.path.abspath(f"tmp_{cfg['error_bound']}.compressed")
        decompressed_file = os.path.abspath(f"tmp_{cfg['error_bound']}.sz.out")
        compress_cmd = sz3_templates["compress_template"].format(
            input=args.input,
            compressed=compressed_file,
            decompressed=decompressed_file,
            dims=dims_flag,
            dimsList=dims_values,
            mode=cfg["mode"],
            arg=cfg["arg"],
            datatype=cfg["datatype"],
            tunning_target_flag=cfg["tunning_target_flag"]
        )

        print(f"[DEBUG] Running compress: {compress_cmd}")
        # print(f"[DEBUG] Running decompress: {decompress_cmd}")
        
        result={}
        result["compressor name"] = "faz"
        result_metrics={}
        
        result_metrics = run_pipeline(
            cfg["name"], 
            {
                "compress_cmd": compress_cmd,
            }, 
            args.input, 
            compressed_file,
            parser = "faz"
        )
        
        if args.enable_calc_stats:

            run_calc_err_stats(
                datatype=cfg["datatype"],
                ori_file=args.input,
                dec_file=decompressed_file,
                dims=[int(d) for d in args.dims.split()],
                block_size=args.block_size,
                shift_size=args.shift_size,
                output_prefix=args.output_prefix
            )     

        
        dtype_map = {
    "-f": "single precision",
    "-d": "double precision"
}
        
        result["input_file"] = input_file_name
        result["data_type"] = dtype_map.get(cfg["datatype"])
        result["compression_ratio"] = result_metrics["compression_ratio"]
        result["compress_time(s)"] = result_metrics["compress_time"]
        result["mode"] = cfg["mode"]
        result["error_bound"] = cfg["error_bound"]
        result["decompress_time(s)"] = result_metrics["decompress_time"]
        result["ori_size(B)"] = result_metrics["size_of_file"]
        

        if args.enable_qcat:
            qcat_results = {}
            qcat_templates = compressor_templates["qcat"]["evaluators"]
            evaluator_keys = args.qcat_evaluators.split(",")
            qcat_results = run_evaluators(
                evaluator_templates=qcat_templates,
                evaluator_keys=evaluator_keys,  # 或根据 args 参数决定哪些分析器
                datatype=args.datatype,
                input=args.input,
                decompressed=decompressed_file,
                dims=args.dims
            )
            print(f"[DEBUG] qcat_results: {qcat_results}")
            result.update(qcat_results)
        results.append(result)   
        
        
        
        
    
        append_result_to_csv(results)
        
        

elif args.compressor == "mgard":
    output_root = "outputs"
    input_path = args.input  

    dataset_name = os.path.basename(os.path.dirname(input_path))      
    input_base, ext = os.path.splitext(os.path.basename(input_path)) 

   
    suffix = f"_{ext[1:].lower()}" if ext else ""

    output_dir = os.path.join(output_root, dataset_name, f"{input_base}{suffix}")
    
    os.makedirs(output_dir, exist_ok=True)
    
    
    name = "mgard"
    dim_list = args.dims.strip().split()
    dims_flag = f"{len(dim_list)}"            
    dims_values = " ".join(dim_list) 

    mgard_templates = compressor_templates["mgard"]

    for cfg in config_registry.get_mgard_configs(args):
        compressed_file = os.path.abspath(f"tmp_{cfg['error_bound']}.compressed")
        decompressed_file = os.path.abspath(f"tmp_{cfg['error_bound']}.mgard.out")

        compress_cmd = mgard_templates["compress_template"].format(
            input=args.input,
            compressed=compressed_file,
            decompressed=decompressed_file,
            dims=dims_flag,
            dimsList=dims_values,
            mode=cfg["mode"],
            arg=cfg["arg"],
            datatype=cfg["datatype"],
            smooth=cfg["smooth"],
            lossless=cfg["lossless"],
            verbose=cfg["verbose"]
        )

        print(f"[DEBUG] Running compress + decompress: {compress_cmd}")

        result = {}
        result_metrics = {}

        result_metrics = run_pipeline(
            cfg["name"],
            {
                "compress_cmd": compress_cmd,
            },
            args.input,
            compressed_file,
            parser="mgard"
        )

        # if args.enable_calc_stats:
        #     run_calc_err_stats(
        #         datatype="-f" if cfg["datatype"] == "s" else "-d", 
        #         # datatype=cfg["datatype"],
        #         # "float" if datatype == "s" else "double",
        #         ori_file=args.input,
        #         dec_file=decompressed_file,
        #         dims=[int(d) for d in args.dims.strip().split()],
        #         block_size=args.block_size,
        #         shift_size=args.shift_size,
        #         output_prefix=args.output_prefix
        #     )

        dtype_map = {
            "s": "single precision",
            "d": "double precision"
        }

        input_file_name = os.path.basename(args.input)
        print("result metrics is: ", result_metrics)
        result["compressor name"] = "mgard"
        result["input_file"] = input_file_name
        result["data_type"] = dtype_map.get(cfg["datatype"])
        result["compression_ratio"] = result_metrics["compression_ratio"]
        result["compress_time(s)"] = result_metrics["compress_time"]
        result["mode"] = cfg["mode"]
        result["error_bound"] = cfg["error_bound"]
        result["decompress_time(s)"] = result_metrics["decompress_time"]
        result["ori_size(B)"] = result_metrics["size_of_file"]

        if args.enable_qcat:
            qcat_results = {}
            qcat_templates = compressor_templates["qcat"]["evaluators"]
            evaluator_keys = args.qcat_evaluators.split(",")
            qcat_results = run_evaluators(
                evaluator_templates=qcat_templates,
                evaluator_keys=evaluator_keys,
                datatype=args.datatype,
                input=args.input,
                decompressed=decompressed_file,
                dims=args.dims
            )
            print(f"[DEBUG] qcat_results: {qcat_results}")
            result.update(qcat_results)

        results.append(result)
        
        

        append_result_to_csv(results)    



df = pd.DataFrame(results)
print("\n Compression Results:")
print(df)
output_dir = "outputs"
os.makedirs(output_dir, exist_ok=True)  # 如果文件夹不存在就创建

df.to_csv(os.path.join(output_dir, name + "_results.csv"), index=False)
df.to_csv(name+"_results.csv", index=False)

