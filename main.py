import yaml
import argparse
import pandas as pd
from runner import run_pipeline
import config_registry
from qcat_runner import run_evaluators

parser = argparse.ArgumentParser()
parser.add_argument("--compressor", required=True, choices=["sz3", "qoz"])
parser.add_argument("--mode", choices=["ABS", "REL"])
parser.add_argument("--value", type=str, help="Single error bound value")
parser.add_argument("--sweep", nargs="*", help="Sweep a list of error bounds")
parser.add_argument("--level", type=int, help="zstd compression level")
parser.add_argument("--dims", type=str, required=True, help="3D data dimensions, e.g. '512 512 512'")
parser.add_argument("--input", required=True)
parser.add_argument("--enable-qcat", action="store_true", help="Enable qcat evaluation")
parser.add_argument("--datatype", choices=["f", "d"], help="Data type for qcat (-f or -d)")
args = parser.parse_args()

compressed_file = "tmp_compressed"
decompressed_file = "tmp_decompressed.sz.out"

with open("configs/compressor_templates.yaml") as f:
    compressor_templates = yaml.safe_load(f)["compressors"]

results = []

if args.compressor == "sz3":
    sz3_templates = compressor_templates["sz3"]
    for cfg in config_registry.get_sz3_configs(args):
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
            decompressed=decompressed_file,
            dims=args.dims,
            mode=cfg["mode"],
            arg=cfg["arg"],
            error_bound=cfg["error_bound"]
        )
        
        result={}
        result["name"] = "sz3"
        result_metrics={}
        # result["compression_ratio"] = run_pipeline(cfg["name"], {
        #     "compress_cmd": compress_cmd,
        # }, args.input, compressed_file, decompressed_file)["compression_ratio"]
        
        result_metrics = run_pipeline(cfg["name"], {
            "compress_cmd": compress_cmd,
            "decompress_cmd": decompress_cmd,
        }, args.input, compressed_file, decompressed_file)
        result["compression_ratio"] = result_metrics["compression_ratio"]
        result["compress_time"] = result_metrics["compress_time"]
        result["mode"] = cfg["mode"]
        result["error_bound"] = cfg["error_bound"]
        results.append(result)

    if args.enable_qcat:
        qcat_templates = compressor_templates["qcat"]["evaluators"]
        run_evaluators(
            evaluator_templates=qcat_templates,
            evaluator_keys=["ssim"],  # 或根据 args 参数决定哪些分析器
            datatype=args.datatype,
            input=args.input,
            decompressed=decompressed_file,
            dims=args.dims
        )
        
        
        
        
        
        
elif args.compressor == "qoz":
    qoz_templates = compressor_templates["qoz"]
    for cfg in config_registry.get_QoZ_configs(args):
        compress_cmd = qoz_templates["compress_template"].format(
            input=args.input,
            compressed=compressed_file,
            dims=args.dims,
            mode=cfg["mode"],
            arg=cfg["arg"],
            error_bound=cfg["error_bound"]
        )
        # decompress_cmd = qoz_templates["decompress_template"].format(
        #     compressed=compressed_file,
        #     decompressed=decompressed_file
        # )
        
        # print("check: ",compress_cmd['arg '])
        result={}
        result["name"] = "qoz"
        result["compression_ratio"] = run_pipeline(cfg["name"], {
            "compress_cmd": compress_cmd,
        }, args.input, compressed_file, decompressed_file)["compression_ratio"]
        result["compress_time"] = run_pipeline(cfg["name"], {
            "compress_cmd": compress_cmd,
        }, args.input, compressed_file, decompressed_file)["compress_time"]
        result["mode"] = cfg["mode"]
        result["error_bound"] = cfg["error_bound"]
        results.append(result)




df = pd.DataFrame(results)
print("\n Compression Results:")
print(df)
df.to_csv("results.csv", index=False)
