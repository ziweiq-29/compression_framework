from compressor_shell import run_command
from metrics import compression_ratio, get_size_orginal

def run_pipeline(name, config, input_path, compressed_path):
    # 运行压缩命令并获取所有信息
    compress_info = run_command(config['compress_cmd'])
    
    # 计算压缩比
    ratio = compression_ratio(input_path, compressed_path)
    
    # 获取原始文件大小
    size = get_size_orginal(input_path)

    # 构造返回结果
    result = {
        "compress_time": round(compress_info.get("compression_time", 0), 4),
        "compression_ratio": round(compress_info.get("compression_ratio", ratio), 4),
        "compressed_file": compress_info.get("compressed_file", compressed_path),
        "decompress_time": round(compress_info.get("decompression_time", 0), 4),
        "decompressed_file": compress_info.get("decompressed_file", ""),
        "size_of_file": size
    }

    return result
