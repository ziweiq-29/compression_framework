"""
RDF on EXAALT: raw vs decompressed → dists.
用法：--standalone --decompressed_x/y/z <path>，读三份解压文件算 RDF，输出 dists。
Uses freud when RDF_USE_FREUD=1; else NumPy RDF.
"""
import argparse
import json
import os
import sys
import numpy as np


_USE_FREUD = False
try:
    if os.environ.get("RDF_USE_FREUD", "").lower() in ("1", "true", "yes"):
        from freud.box import Box
        from freud.density import RDF
        _USE_FREUD = True
except Exception:
    pass

timestep = 0
DEFAULT_NT = 7852
DEFAULT_NA = 1037
DEFAULT_RAW_PREFIX = "/anvil/projects/x-cis240669/EXAALT/SDRBENCH-exaalt-helium/dataset1-7852x1037"


def read_raw_frame(prefix, t, nt, na):
    def load_axis(suffix):
        arr = np.fromfile(f"{prefix}.{suffix}.f32.dat", dtype=np.float32)
        return arr.reshape(nt, na)
    x = load_axis("x")[t]
    y = load_axis("y")[t]
    z = load_axis("z")[t]
    return np.stack([x, y, z], axis=1).astype(np.float32)


def _compute_rdf_numpy(pos, bins=300):
    """Pure NumPy RDF (same interface as freud path)."""
    pos = np.asarray(pos, dtype=np.float64)
    mins = pos.min(axis=0)
    pos = pos - mins
    L = pos.max(axis=0)
    rmax = min(L) / 2
    N = pos.shape[0]
    rho = N / (L[0] * L[1] * L[2])
    edges = np.linspace(0, rmax, bins + 1)
    dr = edges[1] - edges[0]
    # Pairwise distances (upper triangle, no self)
    d = np.sqrt(((pos[:, None, :] - pos[None, :, :]) ** 2).sum(axis=2))
    d = d[np.triu_indices(N, k=1)]
    hist, _ = np.histogram(d, bins=edges)
    hist = hist.astype(np.float64)
    r = (edges[:-1] + edges[1:]) / 2
    vol_shell = 4 * np.pi * (edges[1:] ** 3 - edges[:-1] ** 3) / 3
    ideal = (N / 2) * rho * vol_shell
    np.maximum(ideal, 1e-300, out=ideal)
    g = hist / ideal
    return g


def compute_rdf(pos, bins=300):
    pos = np.asarray(pos, dtype=np.float32)
    mins = pos.min(axis=0)
    pos = pos - mins
    L = pos.max(axis=0)
    box_length = max(L)
    rmax = min(L) / 2
    if _USE_FREUD:
        box = Box.cube(box_length)
        rdf = RDF(bins=bins, r_max=rmax)
        rdf.compute((box, pos))
        return np.asarray(rdf.rdf, dtype=np.float64)
    return _compute_rdf_numpy(pos.astype(np.float64), bins=bins)


def rdf_distance(g1, g2):
    dists=np.abs(g1-g2)
    return dists

def main():
    parser = argparse.ArgumentParser(description="RDF: raw vs decompressed → dists")
    parser.add_argument("--standalone", action="store_true", required=True, help="必须：读三份解压文件")
    parser.add_argument("--decompressed_x", required=True, help="解压后的 x 文件")
    parser.add_argument("--decompressed_y", required=True, help="解压后的 y 文件")
    parser.add_argument("--decompressed_z", required=True, help="解压后的 z 文件")
    parser.add_argument("--raw_prefix", default=DEFAULT_RAW_PREFIX, help=f"Raw .x/.y/.z.f32.dat 前缀 (default: {DEFAULT_RAW_PREFIX})")
    parser.add_argument("--nt", type=int, default=DEFAULT_NT, help=f"时间步数 (default: {DEFAULT_NT})")
    parser.add_argument("--na", type=int, default=DEFAULT_NA, help=f"原子数 (default: {DEFAULT_NA})")
    args = parser.parse_args()

    nt, na = args.nt, args.na
    raw_prefix = args.raw_prefix

    for k in ("decompressed_x", "decompressed_y", "decompressed_z"):
        path = getattr(args, k)
        if not path or not os.path.isfile(path):
            print(f"Missing or not a file: --{k}", file=sys.stderr)
            sys.exit(1)

    coords_dec = np.stack([
        np.fromfile(args.decompressed_x, dtype=np.float32).reshape(nt, na)[timestep],
        np.fromfile(args.decompressed_y, dtype=np.float32).reshape(nt, na)[timestep],
        np.fromfile(args.decompressed_z, dtype=np.float32).reshape(nt, na)[timestep],
    ], axis=1).astype(np.float32)
    coords_raw = read_raw_frame(raw_prefix, timestep, nt, na)
    rdf_raw = compute_rdf(coords_raw)
    rdf_dec = compute_rdf(coords_dec)
    dists = rdf_distance(rdf_raw , rdf_dec)
    # rdf_dir = os.path.dirname(os.path.abspath(__file__))
    np.save(os.path.join("dists.npy"), dists)
    np.save(os.path.join("rdf_raw.npy"), rdf_raw)
    np.save(os.path.join("rdf_dec.npy"), rdf_dec)


if __name__ == "__main__":
    main()