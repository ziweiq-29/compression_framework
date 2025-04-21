import subprocess
import time

def run_command(cmd):
    result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
    
    for line in result.stdout.splitlines():
        if "compression time" in line:
            return float(line.strip().split("=")[-1])
    print(result.stdout)
    
    raise ValueError("Compression time not found in output.")