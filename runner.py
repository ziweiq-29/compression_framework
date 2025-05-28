from compressor_shell import run_command
from metrics import compression_ratio, get_size_orginal
from my_parsers import parse_sz3_output, parse_sperr_output, parse_zfp_output
def get_parser(parser_name):
    parser_map = {
        "sz3": parse_sz3_output,
        "qoz": parse_sz3_output,
        "sperr3d": parse_sperr_output,
        "zfp": parse_zfp_output
    }
    print(f"[DEBUG] get_parser received: '{parser_name}'")
    parser_func = parser_map.get(parser_name)
    if parser_func is None:
        print(f"[ERROR] No parser function found for: '{parser_name}'")
    return parser_func
def run_pipeline(name, config, input_path, compressed_path,parser):

    # 运行压缩命令并获取所有信息
    # compress_info = run_command(config['compress_cmd'])
    parser_func = get_parser(parser)
    compress_info = run_command(config["compress_cmd"], parser_func)
    
    # 计算压缩比
    ratio = compression_ratio(input_path, compressed_path)
    
    # 获取原始文件大小
    size = get_size_orginal(input_path)

    # 构造返回结果
    if name != "zfp":
        result = {
            "compress_time": round(compress_info.get("compression_time", 0), 4),
            "compression_ratio": round(ratio,4),
            "compressed_file": compress_info.get("compressed_file", compressed_path),
            "decompress_time": round(compress_info.get("decompression_time", 0), 4),
            "decompressed_file": compress_info.get("decompressed_file", ""),
            "size_of_file": size
        }
    else:
        result = {
            "compress_time": round(compress_info.get("compression_time", 0), 4),
            "compression_ratio": round(ratio,4),
            # "compressed_file": compress_info.get("compressed_file", compressed_path),
            "decompress_time": round(compress_info.get("decompression_time", 0), 4),
            # "decompressed_file": compress_info.get("decompressed_file", ""),
            "size_of_file": size
        }
    
    return result
    

