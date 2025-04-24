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
        print(f"[QCAT] Running {key.upper()}: {cmd}")
        try:
            completed = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
            output = (completed.stdout or "") + "\n" + (completed.stderr or "")
            print(f"[QCAT] Output:\n{output}")
            for line in output.splitlines():
                line = line.strip()
                if "ssim" in line.lower() and "=" in line:
                    try:
                        _, val = line.split("=")
                        results[f"qcat_{key}"] = float(val.strip())
                        print(f"[QCAT] Parsed {key}: {results[f'qcat_{key}']}")
                    except ValueError:
                        print(f"[QCAT] Warning: could not parse line: {line}")
        except subprocess.CalledProcessError as e:
            print(f"[QCAT] Error running evaluator {key}: {e}")
            print(f"[QCAT] stderr:\n{e.stderr}")
    return results
