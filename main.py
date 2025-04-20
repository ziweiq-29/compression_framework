import yaml
import argparse
import pandas as pd
from runner import run_pipeline
import config_registry

parser = argparse.ArgumentParser()
parser.add_argument("--compressor", required=True, choices=["sz3", "qoz"])
parser.add_argument("--mode", choices=["ABS", "REL"])
parser.add_argument("--value", type=str, help="Single error bound value")
parser.add_argument("--sweep", nargs="*", help="Sweep a list of error bounds")
parser.add_argument("--level", type=int, help="zstd compression level")
parser.add_argument("--dims", type=str, required=True, help="3D data dimensions, e.g. '512 512 512'")
parser.add_argument("--input", required=True)
args = parser.parse_args()

compressed_file = "tmp_compressed"
decompressed_file = "tmp_decompressed"

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
            arg=cfg["arg"]
        )
        # decompress_cmd = sz3_templates["decompress_template"].format(
        #     compressed=compressed_file,
        #     decompressed=decompressed_file
        result = run_pipeline(cfg["name"], {
            "compress_cmd": compress_cmd,
            # "decompress_cmd": decompress_cmd
        }, args.input, compressed_file, decompressed_file)
        result["compressor"] = "sz3"
        results.append(result)
        
elif args.compressor == "qoz":
    qoz_templates = compressor_templates["qoz"]
    for cfg in config_registry.get_QoZ_configs(args):
        compress_cmd = qoz_templates["compress_template"].format(
            input=args.input,
            compressed=compressed_file,
            dims=args.dims,
            mode=cfg["mode"],
            arg=cfg["arg"]
        )
        # decompress_cmd = qoz_templates["decompress_template"].format(
        #     compressed=compressed_file,
        #     decompressed=decompressed_file
        # )
        result = run_pipeline(cfg["name"], {
            "compress_cmd": compress_cmd,
            # "decompress_cmd": decompress_cmd
        }, args.input, compressed_file, decompressed_file)
        result["compressor"] = "qoz"
        results.append(result)




df = pd.DataFrame(results)
print("\n Compression Results:")
print(df)
df.to_csv("results.csv", index=False)
