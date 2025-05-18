import subprocess

def run_command(cmd):
    result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
    output = result.stdout
    info = {}

    for line in output.splitlines():
        line = line.strip()
        if line.startswith("compression ratio"):
            info["compression_ratio"] = float(line.split("=")[-1].strip())
        elif line.startswith("compression time"):
            info["compression_time"] = float(line.split("=")[-1].strip())
        elif line.startswith("compressed data file"):
            info["compressed_file"] = line.split("=")[-1].strip()
        elif line.startswith("decompression time"):
            info["decompression_time"] = float(line.split("=")[-1].strip().split()[0])  # 去掉 "seconds"
        elif line.startswith("decompressed file"):
            info["decompressed_file"] = line.split("=")[-1].strip()

    # 如果缺少某些关键信息，可以抛出错误
    required_keys = ["compression_ratio", "compression_time", "compressed_file", "decompression_time", "decompressed_file"]
    missing_keys = [key for key in required_keys if key not in info]
    if missing_keys:
        print(output)
        raise ValueError(f"Missing required information: {', '.join(missing_keys)}")

    return info
