mode_to_flag = {
    "ABS": "-A",
    "REL": "-R",
    "PSNR": "-S",
    "NORM": "-N",
    # "ABS_AND_REL": "-M",  # 注意：这里要根据你的程序/压缩器实际支持的参数写！
    # "ABS_OR_REL": "-X",   # 同上，确认好
}
dtype_map = {
        "-f": "single precision",
        "-d": "double precision"
    }
def get_sz3_configs(args):
    configs = []
    values = [args.value] if args.value else args.sweep
    for val in values:
        name = f"sz3"
        arg_flag = mode_to_flag[args.mode]
        data_type = f"-{args.datatype}"
        # readable_dtype = dtype_map.get(data_type)
            # data_type = args.datatype
        configs.append({
            "name": name,
            "mode": args.mode,
            "arg": f"{arg_flag} {val}",
            "error_bound": val,
            "datatype": data_type
        })
    return configs

def get_QoZ_configs(args):
    configs = []
    values = [args.value] if args.value else args.sweep
    for val in values:
        name = f"QoZ"
        arg_flag = mode_to_flag[args.mode]
        data_type = f"-{args.datatype}"
        configs.append({
            "name": name,
            "mode": args.mode,
            "arg": f"{arg_flag} {val}",
            "error_bound": val,
            "datatype": data_type  
        })
    return configs
