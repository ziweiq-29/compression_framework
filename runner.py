from compressor_shell import run_command
from metrics import compression_ratio

def run_pipeline(name, config, input_path, compressed_path, decompressed_path):
    t1 = run_command(config['compress_cmd'])
    ratio = compression_ratio(input_path, compressed_path)
    # t2 = run_command(config['decompress_cmd'])

    return {
        "name": name,
        "compress_time": round(t1, 4),
        # "decompress_time": round(t2, 4),
        "compression_ratio": round(ratio, 4)
    }
