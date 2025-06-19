import subprocess

def run_evaluators(evaluator_templates, evaluator_keys, datatype, input, decompressed, dims):
    results = {}
    for key in evaluator_keys:
        if key not in evaluator_templates:
            print(f"[QCAT] Skipping unknown evaluator: {key}")
            continue
        
        cmd = evaluator_templates[key].format(
            datatype=f"-{datatype}",
            input=input,
            decompressed=decompressed,
            dims=dims
        )
        print("key" ,key)
        print("cmd: ",cmd)
        print(f"[QCAT] Running {key.upper()}: {cmd}")
        try:
            completed = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
            output = (completed.stdout or "") + "\n" + (completed.stderr or "")
            print(f"[QCAT] Output:\n{output}")
            if key == 'ssim':
                    for line in output.splitlines():
                        line = line.strip()
                        if "local_ssim" in line.lower() and "=" in line:
                            try:
                                _, val = line.split("=")
                                results["qcat_local_ssim"] = float(val.strip())
                                print(f"[QCAT] Parsed local_ssim: {results['qcat_local_ssim']}")
                            except ValueError:
                                print(f"[QCAT] Warning: could not parse line: {line}")
                        elif "global_ssim" in line.lower() and "=" in line:
                            try:
                                _, val = line.split("=")
                                results["qcat_global_ssim"] = float(val.strip())
                                print(f"[QCAT] Parsed global_ssim: {results['qcat_global_ssim']}")
                            except ValueError:
                                print(f"[QCAT] Warning: could not parse line: {line}")
                                
            elif key == 'computeErrAutoCorrelation':
                for line in output.splitlines():
                    line = line.strip()
                    if line.startswith("Lag-") and "auto correlation:" in line:
                        try:
                            prefix, value = line.rsplit(":", 1)  # ← 使用 rsplit 更安全
                            lag_part = prefix.strip().split()[0]  # e.g. "Lag-1"
                            lag = int(lag_part.split("-")[1])     # 拿到 1
                            val = float(value.strip())            # 转换 value
                            results[f"autocorr_lag_{lag}"] = val
                        except Exception as e:
                            print(f"[QCAT] Parse error for line: {line} ({e})")


            elif key == 'compareData': 
                for line in output.splitlines():
                    line = line.strip()
                    try:                 
                        parts = line.split(",")
                        for part in parts:
                            part = part.strip()
                            if not part:
                                continue
                            if "=" not in part:
                                continue
                            metric, val = part.split("=")
                            metric = metric.strip().lower()
                            val = val.strip()
                            if "max absolute error" in metric:
                                results[f"max_abs_error"] = float(val)
                            elif "max relative error" in metric:
                                results[f"max_rel_error_"] = float(val)
                            elif "max pw relative error" in metric:
                                results[f"max_pw_rel_error"] = float(val)
                            elif "psnr" in metric:
                                results[f"psnr"] = float(val)
                            elif "nrmse" in metric:
                                results[f"nrmse"] = float(val)
                            elif "normerr_norm" in metric:
                                results[f"normerr_norm"] = float(val)
                            elif "normerr" in metric:
                                results[f"normerr"] = float(val)
                            elif "pearson coeff" in metric:
                                results[f"pearson"] = float(val)
                            elif "range" in metric:
                                results["range"] = float(val)
                            # elif "mean squared error" in metric:
                            #     results["mse"] = float(val)
                            elif "original mean" in metric:
                                results["ori_mean"] = float(val)
                            elif "original var" in metric:
                                results["ori_var"] = float(val)
                            elif "original std" in metric:
                                results["ori_std"] = float(val)
                            elif "decompressed mean" in metric:
                                results["dec_mean"] = float(val)
                            elif "decompressed var" in metric:
                                results["dec_var"] = float(val)
                            elif "decompressed std" in metric:
                                results["dec_std"] = float(val)
                            elif "standard deviation of difference" in metric:
                                results["err_std"] = float(val)
                        
                    except ValueError:
                        print(f"[QCAT] Warning: could not parse line: {line}")
                

                    
                    
                    
                    
                    
                    
                    
                    
        except subprocess.CalledProcessError as e:
            print(f"[QCAT] Error running evaluator {key}: {e}")
            print(f"[QCAT] stderr:\n{e.stderr}")
    return results
