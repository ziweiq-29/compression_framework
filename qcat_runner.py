import subprocess

def run_evaluators(evaluator_templates, evaluator_keys, datatype, input, decompressed, dims):
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
        subprocess.run(cmd, shell=True, check=True)
