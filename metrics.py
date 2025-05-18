import os

def compression_ratio(original, compressed):
    o = os.path.getsize(original)
    c = os.path.getsize(compressed)
    return o / c if c else float('inf')
def get_size_orginal(original):
    abs_path = os.path.abspath(original)
    return os.path.getsize(abs_path)
