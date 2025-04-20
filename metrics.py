import os

def compression_ratio(original, compressed):
    o = os.path.getsize(original)
    c = os.path.getsize(compressed)
    return o / c if c else float('inf')
