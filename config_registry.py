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
def get_sperr_configs(args):
    configs = []
    values = [args.value] if args.value else args.sweep
    mode_map = {
        "ABS": "--pwe",
        "REL": "--vre",
        "PSNR": "--psnr",
        "NORM": "--bpp"
    }
    
    # Map ftype from datatype
    ftype_map = {
        "f": "32",
        "d": "64"
    }
    
    for val in values:
        name = f"sperr"
        arg_flag = mode_map[args.mode]
        data_type = ftype_map[args.datatype]
        
        configs.append({
            "name": name,
            "mode": args.mode,
            "arg": f"{arg_flag} {val}",
            "error_bound": val,
            "ftype": data_type,
            "datatype": ftype_map.get(args.datatype)
        })
        

    return configs



def get_zfp_configs(args):
    configs = []

    values = [args.value] if args.value else args.sweep

    # Map compression mode to zfp argument flags
    mode_map = {
        "ABS": "-a",         
        "REL": "-v",        
        "PSNR": "-p",        
        "RATE": "-r",        
        "LOSSLESS": "-R"    
    }


    values = [args.value] if args.value else args.sweep
    for val in values:
        name = f"zfp"
        arg_flag = mode_map[args.mode]
        data_type = f"-{args.datatype}"
        configs.append({
            "name": name,
            "mode": mode_map[args.mode],
            "arg": val,
            "error_bound": val,
            "datatype": data_type  
        })
    return configs






def get_tthresh_configs(args):
    configs = []

    values = [args.value] if args.value else args.sweep

    # Map compression mode to zfp argument flags
    mode_map = {
        "ABS": "-e",         
        "REL": "-r",        
        "PSNR": "-p"       
   
    }
    dtype_map = {
        "f": "float",
        "d": "double",
        "i": "int",
        "uc": "uchar",
        "us": "ushort"
    }
    data_type = dtype_map[args.datatype]
    values = [args.value] if args.value else args.sweep
    for val in values:
        name = f"tthresh"

        configs.append({
            "name": name,
            "mode": mode_map[args.mode],
            "arg": val,
            "error_bound": val,
            "datatype": data_type
        })
    return configs


def get_faz_configs(args):
    configs = []
    values = [args.value] if args.value else args.sweep
    for val in values:
        name = f"faz"
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
