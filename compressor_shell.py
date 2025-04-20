import subprocess
import time

def run_command(cmd):
    start = time.time()
    subprocess.run(cmd, shell=True, check=True)
    end = time.time()
    return end - start
