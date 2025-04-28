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
                    if "ssim" in line.lower() and "=" in line:
                        try:
                            _, val = line.split("=")
                            results[f"qcat_{key}"] = float(val.strip())
                            print(f"[QCAT] Parsed {key}: {results[f'qcat_{key}']}")
                        except ValueError:
                            print(f"[QCAT] Warning: could not parse line: {line}")
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
                    except ValueError:
                        print(f"[QCAT] Warning: could not parse line: {line}")
                

                    
                    
                    
                    
                    
                    
                    
                    
        except subprocess.CalledProcessError as e:
            print(f"[QCAT] Error running evaluator {key}: {e}")
            print(f"[QCAT] stderr:\n{e.stderr}")
    return results
