#!/usr/bin/env python3
"""
One command: pressio decompress + view_cesm_orig_recon PNGs with rich filenames.

Example::

  python run_cesm_case_study.py --compressor sz3 --error-bound 1e-3 \\
    --out-dir /anvil/projects/x-cis240669/DSSIM/case_study/sz3

Reads compression_ratio from STANDARD/.../CLDHGH_00_dat/<compressor>_standard.csv
and dssim from DSSIM/.../CLDHGH_CLDHGH_00_dat/<compressor>_dssim.csv.

View step defaults: **original-only field clim**, **unified |error| vmax** from |original|,
plus **colorbar PNGs** in ``--out-dir``. Override with ``view_cesm_orig_recon.py`` flags forwarded below.

Output stem (no on-image text; three files)::

  <out-dir>/<dataset>_<compressor>_rel<eb>_cr<m>_dssim<s>_{original,decompressed,error}.png

Override paths with --input, --standard-csv-dir, --dssim-csv-dir.

**Same color scale on all error maps (one colorbar in a figure):**

1. Pick a reference ``REL`` (e.g. ``1e-3``) and run::

     python run_cesm_case_study.py --print-error-vmax 1e-3 --unified-error-ref-pct 99

   This prints ``REL × p(ref)|orig|`` (same formula as ``view_cesm_orig_recon`` with
   ``--rel-bound``). Copy the printed number ``V``.

2. Run every compressor with the **same** ``--error-vmax V`` (and your usual
   ``--error-bound`` per method). View uses ``V`` for all; pass the same ``V`` to
   ``--error-vmax`` even when ``--error-bound`` is ``4e-1`` or ``1e-1`` so panels match.

**Batch (four compressors, one command, shared error colorbar):** ::

  python run_cesm_case_study.py --out-dir .../DSSIM/case_study \\
    --case mgard 4e-1 --case sperr 1e-3 --case sz3 1e-3 --case zfp 1e-1 \\
    --shared-error-vmax-rel 1e-3 --unified-error-ref-pct 99

Writes to ``OUT_DIR/<compressor>/`` (lowercase). All error maps use the same
``|error|`` vmax (from ``--error-vmax`` or ``REL×p(ref)|orig|``). Override vmax with
``--error-vmax V`` instead of ``--shared-error-vmax-rel``.
"""

from __future__ import print_function

import argparse
import csv
import math
import os
import re
import subprocess
import sys
import tempfile

from pathlib import Path

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT = os.path.dirname(_SCRIPT_DIR)

DEFAULT_INPUT = os.path.join(_PROJ_ROOT, "CESM", "CLDHGH", "CLDHGH_00.dat")
DEFAULT_STANDARD_DIR = os.path.join(
    _SCRIPT_DIR,
    "outputs",
    "STANDARD",
    "CESM",
    "CLDHGH_00_dat",
)
DEFAULT_DSSIM_DIR = os.path.join(
    _SCRIPT_DIR,
    "outputs",
    "DSSIM",
    "CESM",
    "CLDHGH",
    "CLDHGH_CLDHGH_00_dat",
)
DEFAULT_PRESSIO = os.path.join(
    _PROJ_ROOT,
    "libpressio-env",
    ".spack-env",
    "view",
    "bin",
    "pressio",
)
_VIEW_SCRIPT = os.path.join(_SCRIPT_DIR, "view_cesm_orig_recon.py")
_SAFE_STEM = re.compile(r"[^a-zA-Z0-9._-]+")


def safe_filename_token(s):
    t = _SAFE_STEM.sub("_", str(s).strip()).strip("_")
    return t if t else "na"


def _eb_float(x):
    return float(str(x).strip().lower().replace("d", "e"))


def _error_bounds_match(a, b):
    try:
        return math.isclose(_eb_float(a), _eb_float(b), rel_tol=1e-9, abs_tol=1e-15)
    except (TypeError, ValueError):
        return False


def _parse_csv_float(cell):
    if cell is None:
        return None
    s = str(cell).strip()
    if not s or s.lower() in ("<empty>", "nan", "none"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def lookup_compression_ratio(standard_dir, compressor, error_bound, input_basename):
    p = Path(standard_dir) / "{}_standard.csv".format(compressor.strip().lower())
    if not p.is_file():
        return None
    ck = compressor.strip().lower()
    raw_bn = os.path.basename(input_basename)
    fallback = None
    try:
        with open(str(p), newline="") as f:
            rdr = csv.DictReader(f)
            for row in rdr:
                cn = (row.get("compressor name") or "").strip().lower()
                if cn != ck:
                    continue
                if not _error_bounds_match(row.get("error_bound", ""), error_bound):
                    continue
                cr = _parse_csv_float(row.get("compression_ratio", ""))
                if cr is None:
                    continue
                inp = (row.get("input") or "").strip()
                if inp and os.path.basename(inp) != raw_bn and inp != raw_bn:
                    if fallback is None:
                        fallback = cr
                    continue
                return cr
    except (EnvironmentError, ValueError):
        return None
    return fallback


def lookup_dssim(dssim_dir, compressor, error_bound, input_basename):
    p = Path(dssim_dir) / "{}_dssim.csv".format(compressor.strip().lower())
    if not p.is_file():
        return None
    ck = compressor.strip().lower()
    raw_bn = os.path.basename(input_basename)
    fallback = None
    try:
        with open(str(p), newline="") as f:
            rdr = csv.DictReader(f)
            for row in rdr:
                cn = (row.get("compressor name") or "").strip().lower()
                if cn != ck:
                    continue
                if not _error_bounds_match(row.get("error_bound", ""), error_bound):
                    continue
                d = _parse_csv_float(row.get("dssim", ""))
                if d is None:
                    continue
                inp = (row.get("input") or "").strip()
                if inp and os.path.basename(inp) != raw_bn and inp != raw_bn:
                    if fallback is None:
                        fallback = d
                    continue
                return d
    except (EnvironmentError, ValueError):
        return None
    return fallback


def float_metric_token(x):
    """e.g. 18.7094 -> 18p7094 (for filenames)."""
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "na"
    s = "{:.6g}".format(float(x))
    return s.replace(".", "p")


def build_output_stem(input_path, compressor, error_key, error_bound, cr, dssim):
    base = Path(input_path).stem
    eb_tok = safe_filename_token(error_bound)
    ek = safe_filename_token(error_key)
    parts = [
        safe_filename_token(base),
        safe_filename_token(compressor),
        "{}{}".format(ek, eb_tok),
        "cr{}".format(float_metric_token(cr)),
        "dssim{}".format(float_metric_token(dssim)),
    ]
    return "_".join(parts)


def resolve_view_python():
    ovr = os.environ.get("CESM_VIEW_PYTHON", "").strip()
    cands = []
    if ovr:
        cands.append(ovr)
    cands.extend(
        [
            os.path.join(_SCRIPT_DIR, "outputs", ".plot_env", "bin", "python"),
            os.path.join(_PROJ_ROOT, "HEDM", "hedm-viz-env39", "bin", "python"),
        ]
    )
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return "python3"


def compute_shared_error_vmax_float(in_path, dims, dtype_s, pref, rel_s):
    """
    REL × p(pref)|orig|; same as view_cesm unified + --rel-bound REL.
    Returns float vmax.
    """
    rel_s = str(rel_s).strip()
    try:
        rel = _eb_float(rel_s)
    except (TypeError, ValueError):
        raise SystemExit("Invalid REL {!r}".format(rel_s))
    if rel <= 0.0:
        raise SystemExit("REL must be positive, got {!r}".format(rel_s))

    in_path = os.path.abspath(os.path.expanduser(in_path))
    if not os.path.isfile(in_path):
        raise SystemExit("Missing input: {}".format(in_path))

    n0, n1 = int(dims[0]), int(dims[1])
    pref = float(pref)
    py = resolve_view_python()
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    snippet = (
        "import numpy as np,sys,os;"
        "rel=float(sys.argv[1]);p=sys.argv[2];n0=int(sys.argv[3]);n1=int(sys.argv[4]);"
        "dtk=sys.argv[5].lower();pref=float(sys.argv[6]);"
        "item=4 if dtk in ('float','float32','f32') else 8;"
        "dt=np.float32 if item==4 else np.float64;"
        "el=n0*n1*item;"
        "sz=os.stat(p).st_size;"
        "sz!=el and sys.exit('%s: size %s != %dx%dx%d bytes'%(p,sz,n0,n1,item));"
        "a=np.fromfile(p,dtype=dt).reshape(n0,n1);"
        "o=float(np.percentile(np.abs(a.ravel()),pref));"
        "o=o if (np.isfinite(o) and o>0) else (float(np.max(np.abs(a.ravel()))) or 1.0);"
        "vmax=rel*o;"
        "print(repr(vmax))"
    )
    cmd = [
        py,
        "-c",
        snippet,
        str(rel),
        in_path,
        str(n0),
        str(n1),
        str(dtype_s),
        str(pref),
    ]
    out = subprocess.check_output(cmd, env=env, universal_newlines=True)
    line = out.strip().splitlines()[-1]
    return float(line)


def print_shared_error_vmax(args):
    """Print REL×p(ref)|orig| for --input; same as view unified + --rel-bound REL."""
    rel_s = str(args.print_error_vmax).strip()
    in_path = os.path.abspath(os.path.expanduser(args.input))
    pref = float(args.unified_error_ref_pct)
    vmax = compute_shared_error_vmax_float(
        in_path, args.dims, args.dtype, pref, rel_s
    )
    print(
        "[case-study] Shared |error| vmax = {} × p{}(|orig|) = {:.12g}".format(
            rel_s, pref, vmax
        ),
        flush=True,
    )
    print(
        "[case-study] Use on every run:  --error-vmax {:.12g}  "
        "(same --unified-error-ref-pct as above)".format(vmax),
        flush=True,
    )


def run_pressio(pressio_bin, in_path, recon_path, compressor, error_key, error_bound, d0, d1, dtype_t):
    cmd = [
        str(pressio_bin),
        "-i",
        os.path.abspath(in_path),
        "-b",
        "compressor={}".format(compressor),
        "-o",
        "{}={}".format(error_key, error_bound),
        "-d",
        str(int(d0)),
        "-d",
        str(int(d1)),
        "-t",
        str(dtype_t),
        "-W",
        os.path.abspath(recon_path),
    ]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    print("[case-study] pressio: {}".format(" ".join(cmd)), flush=True)
    subprocess.run(cmd, check=True, env=env)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Run pressio -W + view_cesm_orig_recon with metrics in PNG filename stem."
    )
    ap.add_argument(
        "--compressor",
        default=None,
        help="LibPressio compressor name (e.g. sz3). Required unless --print-error-vmax.",
    )
    ap.add_argument(
        "--error-bound",
        default=None,
        help="Value bound (e.g. 1e-3). Required unless --print-error-vmax.",
    )
    ap.add_argument(
        "--out-dir",
        default=None,
        help="Output directory for recon temp + three PNGs. Required unless --print-error-vmax.",
    )
    ap.add_argument(
        "--print-error-vmax",
        default=None,
        metavar="REL",
        help=(
            "Print REL×p(ref)|orig| for --input/--dims (matches view_cesm unified+rel_bound) and exit. "
            "Use the printed value as the same --error-vmax on each compressor for one shared error colorbar."
        ),
    )
    ap.add_argument(
        "--case",
        nargs=2,
        metavar=("COMPRESSOR", "ERROR_BOUND"),
        action="append",
        default=None,
        help=(
            "Batch mode: one compressor and its pressio bound (repeat flag). "
            "Requires --out-dir; writes OUT_DIR/<compressor>/. Do not combine with --compressor/--error-bound."
        ),
    )
    ap.add_argument(
        "--shared-error-vmax-rel",
        default=None,
        metavar="REL",
        help=(
            "Batch mode: shared |error| vmax = REL×p(ref)|orig| for every case. "
            "Ignored if --error-vmax is set. Default REL in batch is 1e-3 when neither is given."
        ),
    )
    ap.add_argument("--input", default=DEFAULT_INPUT, help="Original CESM .dat (float32).")
    ap.add_argument(
        "--error-key",
        default="rel",
        choices=("rel", "abs", "pw_rel"),
        help="pressio -o key (default rel).",
    )
    ap.add_argument(
        "--standard-csv-dir",
        default=DEFAULT_STANDARD_DIR,
        help="Directory with <compressor>_standard.csv (default: project STANDARD CLDHGH_00_dat).",
    )
    ap.add_argument(
        "--dssim-csv-dir",
        default=DEFAULT_DSSIM_DIR,
        help="Directory with <compressor>_dssim.csv (default: project DSSIM CLDHGH_CLDHGH_00_dat).",
    )
    ap.add_argument(
        "--pressio-bin",
        default=os.environ.get("PRESSIO", DEFAULT_PRESSIO),
        help="pressio executable (default: $PRESSIO or project libpressio-env).",
    )
    ap.add_argument(
        "--dims",
        nargs=2,
        type=int,
        default=[3600, 1800],
        metavar=("D0", "D1"),
        help="pressio -d values (default 3600 1800).",
    )
    ap.add_argument("--dtype", default="float", help="pressio -t (default float).")
    ap.add_argument(
        "--keep-recon",
        action="store_true",
        help="Keep temporary reconstructed .dat in out-dir instead of deleting.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print stem and metrics only; do not run pressio or plotting.",
    )
    ap.add_argument(
        "--data-clim",
        choices=("pooled", "original"),
        default="original",
        help="Passed to view (default original: field scale from original only).",
    )
    ap.add_argument(
        "--error-scale",
        choices=("unified", "percentile"),
        default="unified",
        help="Passed to view (default unified: |error| vmax from |orig|, not compressor/eb).",
    )
    ap.add_argument(
        "--unified-error-fraction",
        type=float,
        default=0.02,
        metavar="F",
        help="Passed to view: vmax = F × p(ref)|orig| for unified error maps (default 0.02).",
    )
    ap.add_argument(
        "--unified-error-ref-pct",
        type=float,
        default=99.9,
        metavar="P",
        help="Passed to view: reference percentile on |orig| for unified error vmax (default 99.9).",
    )
    ap.add_argument(
        "--error-vmax",
        type=float,
        default=None,
        metavar="V",
        help=(
            "Passed to view: fixed |error| vmax. In batch mode, applies to every --case. "
            "Overrides --shared-error-vmax-rel. Single-mode: suggested V from --print-error-vmax REL."
        ),
    )
    ap.add_argument(
        "--no-colorbars",
        action="store_true",
        help="Passed to view: skip writing *colorbar_*.png legends.",
    )
    args = ap.parse_args(argv)

    if args.print_error_vmax is not None:
        print_shared_error_vmax(args)
        return 0

    if args.case:
        if args.compressor is not None or args.error_bound is not None:
            raise SystemExit("error: use --case ... for batch mode, not --compressor/--error-bound")
        if not args.out_dir:
            raise SystemExit("error: batch mode requires --out-dir (parent directory for per-compressor subdirs)")
        return run_batch_cases(args)

    if args.compressor is None or args.error_bound is None or args.out_dir is None:
        raise SystemExit(
            "error: --compressor, --error-bound, and --out-dir are required "
            "(or --case for batch, or --print-error-vmax REL only)."
        )

    in_path = os.path.abspath(os.path.expanduser(args.input))
    if not os.path.isfile(in_path):
        raise SystemExit("Missing input: {}".format(in_path))

    out_dir = os.path.abspath(os.path.expanduser(args.out_dir))
    os.makedirs(out_dir, mode=0o755, exist_ok=True)

    run_one_case(
        args,
        in_path,
        out_dir,
        args.compressor.strip(),
        str(args.error_bound).strip(),
        forced_error_vmax=args.error_vmax,
    )
    return 0


def run_batch_cases(args):
    in_path = os.path.abspath(os.path.expanduser(args.input))
    if not os.path.isfile(in_path):
        raise SystemExit("Missing input: {}".format(in_path))

    parent = os.path.abspath(os.path.expanduser(args.out_dir))
    os.makedirs(parent, mode=0o755, exist_ok=True)

    pref = float(args.unified_error_ref_pct)
    if args.error_vmax is not None:
        shared_v = float(args.error_vmax)
        print(
            "[case-study] batch: shared |error| vmax = {:.12g} (--error-vmax)".format(shared_v),
            flush=True,
        )
    else:
        rel_ref = args.shared_error_vmax_rel if args.shared_error_vmax_rel is not None else "1e-3"
        shared_v = compute_shared_error_vmax_float(
            in_path, args.dims, args.dtype, pref, rel_ref
        )
        print(
            "[case-study] batch: shared |error| vmax = {:.12g} "
            "({} × p{}(|orig|))".format(shared_v, rel_ref, pref),
            flush=True,
        )

    for comp_raw, eb_raw in args.case:
        comp = comp_raw.strip()
        eb = str(eb_raw).strip()
        sub = os.path.join(parent, comp.lower())
        os.makedirs(sub, mode=0o755, exist_ok=True)
        print("[case-study] batch: --- {}  error_bound={}  out={} ---".format(comp, eb, sub), flush=True)
        run_one_case(args, in_path, sub, comp, eb, forced_error_vmax=shared_v)

    print("[case-study] batch: done ({} cases)".format(len(args.case)), flush=True)
    return 0


def run_one_case(args, in_path, out_dir, comp, eb, forced_error_vmax=None):
    """Run pressio + view for one compressor/bound. forced_error_vmax forces view color scale when set."""
    raw_bn = os.path.basename(in_path)

    cr = lookup_compression_ratio(args.standard_csv_dir, comp, eb, raw_bn)
    dssim_v = lookup_dssim(args.dssim_csv_dir, comp, eb, raw_bn)
    print(
        "[case-study] metrics: compression_ratio={} dssim={}".format(
            cr if cr is not None else "na",
            dssim_v if dssim_v is not None else "na",
        ),
        flush=True,
    )

    stem = build_output_stem(in_path, comp, args.error_key, eb, cr, dssim_v)
    png_name = "{}.png".format(safe_filename_token(stem))
    if args.dry_run:
        print("[case-study] dry-run stem → {}  (--save {})".format(stem, png_name), flush=True)
        return

    fd, recon_path = tempfile.mkstemp(prefix="recon_", suffix=".dat", dir=out_dir)
    os.close(fd)
    try:
        run_pressio(
            args.pressio_bin,
            in_path,
            recon_path,
            comp,
            args.error_key,
            eb,
            args.dims[0],
            args.dims[1],
            args.dtype,
        )
        py = resolve_view_python()
        vcmd = [
            py,
            _VIEW_SCRIPT,
            in_path,
            recon_path,
            "--save",
            png_name,
            "--out-dir",
            out_dir,
            "--data-clim",
            args.data_clim,
            "--error-scale",
            args.error_scale,
            "--unified-error-fraction",
            str(args.unified_error_fraction),
            "--unified-error-ref-pct",
            str(args.unified_error_ref_pct),
        ]
        ev = forced_error_vmax if forced_error_vmax is not None else args.error_vmax
        if ev is not None:
            vcmd.extend(["--error-vmax", str(ev)])
        elif args.error_key == "rel" or args.error_key == "pw_rel":
            vcmd.extend(["--rel-bound", eb])
        elif args.error_key == "abs":
            vcmd.extend(["--error-vmax", eb])
        if args.no_colorbars:
            vcmd.append("--no-colorbars")
        print("[case-study] view: {}".format(" ".join(vcmd)), flush=True)
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        subprocess.run(vcmd, check=True, env=env)
    finally:
        if not args.keep_recon and os.path.isfile(recon_path):
            try:
                os.unlink(recon_path)
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main() or 0)
