def get_sz3_configs(args):
    configs = []
    values = [args.value] if args.value else args.sweep
    for val in values:
        name = f"sz3"
        arg_flag = "-A" if args.mode == "ABS" else "-R"
        configs.append({
            "name": name,
            "mode": args.mode,
            "arg": f"{arg_flag} {val}",
            "error_bound": {val}
        })
    return configs

def get_QoZ_configs(args):
    configs = []
    values = [args.value] if args.value else args.sweep
    for val in values:
        name = f"QoZ"
        arg_flag = "-A" if args.mode == "ABS" else "-R"
        configs.append({
            "name": name,
            "mode": args.mode,
            "arg": f"{arg_flag} {val}",
            "error_bound": val
        })
    return configs
