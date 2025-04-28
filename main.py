import yaml
import argparse
import pandas as pd
from runner import run_pipeline
import config_registry
import os
from qcat_runner import run_evaluators


parser = argparse.ArgumentParser()
parser.add_argument("--compressor", required=True, choices=["sz3", "qoz"])
parser.add_argument("--mode", choices=["ABS", "REL","PSNR","NORM"])
parser.add_argument("--value", type=str, help="Single error bound value")
parser.add_argument("--sweep", nargs="*", help="Sweep a list of error bounds")
parser.add_argument("--level", type=int, help="zstd compression level")
parser.add_argument("--dims", type=str, required=True, help="3D data dimensions, e.g. '512 512 512'")
parser.add_argument("--input", required=True)
parser.add_argument("--enable-qcat", action="store_true", help="Enable qcat evaluation")
parser.add_argument("--datatype", choices=["f", "d"], help="Data type for qcat (-f or -d)")
parser.add_argument("--qcat-evaluators", type=str, default="ssim,compareData",
                    help="Comma-separated list of qcat evaluators to use (default: 'ssim,compareData')")
args = parser.parse_args()

compressed_file = "tmp_compressed"
args.input = os.path.abspath(args.input)
decompressed_file = os.path.abspath("tmp_decompressed.sz.out")

with open("configs/compressor_templates.yaml") as f:
    compressor_templates = yaml.safe_load(f)["compressors"]

if args.compressor == "sz3":
    results = []
    
    sz3_templates = compressor_templates["sz3"]
    for cfg in config_registry.get_sz3_configs(args):
        compressed_file = os.path.abspath(f"tmp_{cfg['error_bound']}.compressed")
        decompressed_file = os.path.abspath(f"tmp_{cfg['error_bound']}.sz.out")
        compress_cmd = sz3_templates["compress_template"].format(
            input=args.input,
            compressed=compressed_file,
            dims=args.dims,
            mode=cfg["mode"],
            arg=cfg["arg"],
            error_bound=cfg["error_bound"]
        )
        decompress_cmd = sz3_templates["decompress_template"].format(
            input=args.input,
            compressed=compressed_file,
            decompressed=decompressed_file,
            dims=args.dims,
            mode=cfg["mode"],
            arg=cfg["arg"],
            error_bound=cfg["error_bound"]
        )
        print(f"[DEBUG] Running compress: {compress_cmd}")
        # print(f"[DEBUG] Running decompress: {decompress_cmd}")
        
        result={}
        result["compressor name"] = "sz3"
        result_metrics={}
        
        result_metrics = run_pipeline(cfg["name"], {
            "compress_cmd": compress_cmd,
            "decompress_cmd": decompress_cmd,
        }, args.input, compressed_file, decompressed_file)
        
        if not os.path.exists(decompressed_file):
            print(f"[ERROR] Decompression failed, missing output file: {decompressed_file}")
            continue
        
        result["compression_ratio"] = result_metrics["compression_ratio"]
        result["compress_time"] = result_metrics["compress_time"]
        result["mode"] = cfg["mode"]
        result["error_bound"] = cfg["error_bound"]
        

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
            # print(f"[DEBUG] qcat_results: {qcat_results}")
            result.update(qcat_results)
        results.append(result)   

        
        
        
        
        
        
elif args.compressor == "qoz":
    results = []
    
    
    qoz_templates = compressor_templates["qoz"]
    for cfg in config_registry.get_QoZ_configs(args):
        compressed_file = os.path.abspath(f"tmp_{cfg['error_bound']}.qoz")
        decompressed_file = os.path.abspath(f"tmp_{cfg['error_bound']}.qoz.out")
        compress_cmd = qoz_templates["compress_template"].format(
            input=args.input,
            compressed=compressed_file,
            dims=args.dims,
            mode=cfg["mode"],
            arg=cfg["arg"],
            error_bound=cfg["error_bound"]
        )
        # print(f"[DEBUG] Running compress: {compress_cmd}")
        decompress_cmd = qoz_templates["decompress_template"].format(
            input=args.input,
            compressed=compressed_file,
            decompressed=decompressed_file,
            dims=args.dims,
            mode=cfg["mode"],
            arg=cfg["arg"],
            error_bound=cfg["error_bound"]
        )
        # print(f"[DEBUG] Running decompress: {decompress_cmd}")
        # print(f"[DEBUG] Expecting decompressed file: {decompressed_file}")
        result={}
        result["compressor name"] = "qoz"
        result_metrics = {}
        
        result_metrics = run_pipeline(cfg["name"], {
            "compress_cmd": compress_cmd,
            "decompress_cmd": decompress_cmd,
        }, args.input, compressed_file, decompressed_file)
        
        if not os.path.exists(decompressed_file):
            print(f"[ERROR] Decompression failed, missing output file: {decompressed_file}")
            continue
        
        result["compression_ratio"] = result_metrics["compression_ratio"]
        result["compress_time"] = result_metrics["compress_time"]
        result["mode"] = cfg["mode"]
        result["error_bound"] = cfg["error_bound"]
        
        
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
        





df = pd.DataFrame(results)
print("\n Compression Results:")
print(df)
df.to_csv("results.csv", index=False)

