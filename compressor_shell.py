import subprocess
from my_parsers import parse_sz3_output, parse_sperr_output


def run_command(cmd,parser_func):
   
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        output = result.stdout
    except subprocess.CalledProcessError as e:
        print("[ERROR] Compression command failed.")
        print(f"[ERROR] Exit code: {e.returncode}")
        print(f"[ERROR] Command: {e.cmd}")
        print("========== STDOUT ==========")
        print(e.stdout)
        print("========== STDERR ==========")
        print(e.stderr)
        raise  # 保留异常抛出，调用者可以决定怎么处理
    info = parser_func(output)
    for line in output.splitlines():
        line = line.strip()
        # if line.startswith("compression ratio"):
        #     info["compression_ratio"] = float(line.split("=")[-1].strip())
        if line.startswith("compression time"):
            info["compression_time"] = float(line.split("=")[-1].strip())
        elif line.startswith("compressed data file"):
            info["compressed_file"] = line.split("=")[-1].strip()
        elif line.startswith("decompression time"):
            info["decompression_time"] = float(line.split("=")[-1].strip().split()[0])  # 去掉 "seconds"
        elif line.startswith("decompressed file"):
            info["decompressed_file"] = line.split("=")[-1].strip()

    # 如果缺少某些关键信息，可以抛出错误
    # required_keys = [ "compression_time", "compressed_file", "decompression_time", "decompressed_file"]
    # missing_keys = [key for key in required_keys if key not in info]
    # if missing_keys:
    #     print(output)
    #     raise ValueError(f"Missing required information: {', '.join(missing_keys)}")

    return info
