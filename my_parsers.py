def parse_sz3_output(output):
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
            info["decompression_time"] = float(line.split("=")[-1].strip().split()[0])
        elif line.startswith("decompressed file"):
            info["decompressed_file"] = line.split("=")[-1].strip()
    return info


def parse_sperr_output(output):
    info = {}
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("Compression time ="):
            info["compression_time"] = float(line.split("=")[-1].strip().rstrip("s"))
        elif line.startswith("Decompression time ="):
            info["decompression_time"] = float(line.split("=")[-1].strip().rstrip("s"))
        elif "Compression ratio =" in line:
            parts = line.split("Compression ratio =")
            if len(parts) > 1:
                ratio_str = parts[1].split(",")[0].strip()
                info["compression_ratio"] = float(ratio_str)
    return info

