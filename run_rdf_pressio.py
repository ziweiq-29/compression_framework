#!/usr/bin/env python3
import argparse
import csv
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime

# === 固定路径（按你现在的环境） ===
RDF_DIR = os.path.expanduser("/anvil/projects/x-cis240669/RDF")
RDF_PIPELINE = os.path.join(RDF_DIR, "run_pressio_external.py")
RDF_PYTHON = "/anvil/projects/x-cis240669/RDF/rdf_env/bin/python"
PRESSIO = "/anvil/projects/x-cis240669/libpressio-env/.spack-env/view/bin/pressio"

# === 只解析 pressio 输出的 [QOI] 行（不做计算）===
QOI_PATTERNS = {
    "mean": r"\[QOI\]\s+mean\s*:\s*([0-9.eE+-]+)",
    "min": r"\[QOI\]\s+min\s*:\s*([0-9.eE+-]+)",
    "max": r"\[QOI\]\s+max\s*:\s*([0-9.eE+-]+)",
    "median": r"\[QOI\]\s+median\s*:\s*([0-9.eE+-]+)",
    "p90": r"\[QOI\]\s+p90\s*:\s*([0-9.eE+-]+)",
    "p99": r"\[QOI\]\s+p99\s*:\s*([0-9.eE+-]+)",
    "p999": r"\[QOI\]\s+p999\s*:\s*([0-9.eE+-]+)",
    "wasserstein_distance": r"\[QOI\]\s+wasserstein_distance\s*:\s*([0-9.eE+-]+)",
}

# Emitted by RDF/run_pressio_rdf_pipeline.py around run_pressio_rdf.py subprocess.
EXAALT_APP_EVAL_RE = re.compile(r"\[EXAALT_APP\]\s+app_eval_sec=([0-9.eE+-]+)", re.IGNORECASE)

def output_csv_path(output_dir: str, compressor: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    return os.path.join(output_dir, f"{compressor}_rdf.csv")

def write_debug_log(output_dir: str, compressor: str, eb: str, text: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(output_dir, f"debug_qoi_{compressor}_rel{eb}_{ts}.log")
    with open(path, "w") as f:
        f.write(text)
    return path

def parse_qoi_from_text(text: str):
    """只解析，不计算。取每个字段最后一次出现的值。"""
    out = {}
    for k, pat in QOI_PATTERNS.items():
        m = re.findall(pat, text)
        out[k] = float(m[-1]) if m else None
    return out


def write_rdf_csv(output_csv: str, fieldnames: list, old_rows: list) -> None:
    """把当前 old_rows 完整写回 CSV（与循环结束写一致）。用于每跑完一个 eb 就落盘，避免 time limit / 断线丢全部。"""
    os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in old_rows:
            for k in fieldnames:
                if k not in row:
                    row[k] = ""
            writer.writerow(row)
    try:
        os.sync()  # 尽量刷到 NFS；忽略不支持的平台
    except Exception:
        pass

def main():
    ap = argparse.ArgumentParser(description="Run RDF external and parse [QOI] lines into CSV (no computation).")
    ap.add_argument("--input", required=True, help="Prefix path (no .x/.y/.z suffix), e.g. .../10x32000")
    ap.add_argument("--dims", nargs="+", required=True, help="Dims: nt na")
    ap.add_argument("--error-bounds", nargs="+", required=True, help="Error bounds list, e.g. 1e-3 5e-4")
    ap.add_argument("--compressor", default="sz3")
    ap.add_argument("--datatype", default="float")  # 保留接口，当前不用
    ap.add_argument("--output-dir", "-o", required=True, help="Output folder; CSV name is <compressor>_rdf.csv")
    ap.add_argument("--pressio-opts", action="append", default=[],
                    help='Forward to run_pressio_external.py. Can repeat. Example: --pressio-opts "sz3:algorithm_str=ALGO_BIOMD"')
    ap.add_argument("--print-output-on-fail", action="store_true",
                    help="If QOI missing, also print last ~2000 chars to stderr for quick glance.")
    args = ap.parse_args()

    input_prefix = os.path.abspath(args.input)
    nt, na = int(args.dims[0]), int(args.dims[1])

    output_csv = output_csv_path(args.output_dir, args.compressor)
    print(f"[RDF] Writing results to {output_csv}")

    fieldnames = ["compressor name", "input", "error_bound", "app_eval_sec"] + list(
        QOI_PATTERNS.keys()
    )

    # 数值标准化，避免 1e-3 和 0.001 被当成不同（参考 main.append_result_to_csv）
    def norm(v):
        try:
            return "{:.12g}".format(float(v))
        except Exception:
            return str(v).strip() if v is not None else ""

    # 读取已有 CSV，按 (compressor name, input, error_bound) 建索引
    old_rows = []
    if os.path.exists(output_csv):
        try:
            with open(output_csv, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                old_rows = list(reader)
        except Exception:
            old_rows = []

    index = {}
    for row in old_rows:
        comp = str(row.get("compressor name", "")).strip()
        inp = str(row.get("input", "")).strip()
        eb_val = norm(row.get("error_bound", ""))
        if comp and inp and eb_val:
            index[(comp, inp, eb_val)] = row

    def has_app_eval_sec(row: dict) -> bool:
        v = row.get("app_eval_sec", "")
        if v is None:
            return False
        if isinstance(v, str) and not str(v).strip():
            return False
        return True

    force_app_eval = os.environ.get("EXAALT_FORCE_APP_EVAL", "").strip().lower() in ("1", "true", "yes")
    if force_app_eval:
        print("[RDF] EXAALT_FORCE_APP_EVAL=1: recompute app_eval_sec + QOI", flush=True)

    compressor_name = args.compressor
    input_basename = os.path.basename(input_prefix)
    added_rows = 0
    updated_rows = 0

    def checkpoint():
        write_rdf_csv(output_csv, fieldnames, old_rows)
        print(f"[RDF] checkpoint: wrote {output_csv} ({len(old_rows)} row(s))", flush=True)

    try:
        for eb in args.error_bounds:
            key = (compressor_name, input_basename, norm(eb))
            if key in index and has_app_eval_sec(index[key]) and not force_app_eval:
                print(f"[RDF] skip existing compressor={compressor_name} input={input_basename} error_bound={eb}")
                continue

            print(f"[RDF] {input_basename} | rel={eb}")

            cmd = [
                "env", "-u", "PYTHONPATH",
                RDF_PYTHON, RDF_PIPELINE,
                "--clean-tmp",
                "--prefix", input_prefix,
                "--nt", str(nt),
                "--na", str(na),
                "--rel", str(eb),
                "--compressor", args.compressor,
                "--pressio", PRESSIO,
            ]
            for opt in args.pressio_opts:
                cmd += ["--pressio-opts", opt]

            # 不能对 run_pressio_external 用 PIPE：z 轴 pressio 会大量写 stdout，管道塞满后子进程阻塞 → 死锁。
            # 写到临时文件再读，既保留完整日志供解析，又避免 PIPE 背压。
            with tempfile.NamedTemporaryFile(
                mode="w+", suffix=".log", delete=False, encoding="utf-8", errors="replace"
            ) as tf:
                log_path_run = tf.name
            try:
                with open(log_path_run, "w", encoding="utf-8", errors="replace") as out_f:
                    proc = subprocess.run(
                        cmd,
                        stdout=out_f,
                        stderr=subprocess.STDOUT,
                        cwd=RDF_DIR,
                    )
                with open(log_path_run, "r", encoding="utf-8", errors="replace") as f:
                    combined = f.read()
            finally:
                try:
                    os.unlink(log_path_run)
                except OSError:
                    pass

            if proc.returncode != 0:
                print(f"[ERROR] RDF pipeline failed for eb={eb} (returncode={proc.returncode})", file=sys.stderr)
                if not (combined or "").strip():
                    combined = (
                        f"(no stdout/stderr captured; returncode={proc.returncode})\n"
                        f"Hint: run manually in RDF dir: {RDF_PYTHON} {RDF_PIPELINE} --clean-tmp --prefix ... --nt {nt} --na {na} --rel {eb} --compressor {args.compressor} --pressio {PRESSIO}\n"
                    )
                log_path = write_debug_log(args.output_dir, args.compressor, str(eb), combined)
                print(f"[ERROR] Full output saved to: {log_path}", file=sys.stderr)
                continue

            qoi = parse_qoi_from_text(combined)
            app_chunks = [float(m) for m in EXAALT_APP_EVAL_RE.findall(combined)]
            app_eval_str = "{:.15g}".format(sum(app_chunks)) if app_chunks else ""
            if not app_chunks:
                print(
                    "[WARN] No [EXAALT_APP] app_eval_sec lines in output; "
                    "check RDF/run_pressio_rdf_pipeline.py",
                    file=sys.stderr,
                )

            row = {
                "compressor name": args.compressor,
                "input": input_basename,
                "error_bound": eb,
                "app_eval_sec": app_eval_str,
                **qoi,
            }

            missing = [k for k, v in qoi.items() if v is None]
            if missing:
                print(f"[WARN] Missing QOI field(s): {missing}")
                log_path = write_debug_log(args.output_dir, args.compressor, str(eb), combined)
                print(f"[WARN] Full output saved to: {log_path}")
                if args.print_output_on_fail:
                    tail = combined[-2000:] if len(combined) > 2000 else combined
                    print("----- output tail -----", file=sys.stderr)
                    print(tail, file=sys.stderr)
                    print("-----------------------", file=sys.stderr)

            # 合并到 old_rows：若 key 已存在则更新，否则追加
            if key in index:
                target = index[key]
                for k, v in row.items():
                    if k == "app_eval_sec":
                        if v is not None and v != "":
                            target[k] = v
                    elif v is not None and str(target.get(k, "")).strip() == "":
                        target[k] = v
                updated_rows += 1
            else:
                full_row = {k: row.get(k, "") for k in fieldnames}
                old_rows.append(full_row)
                index[key] = full_row
                added_rows += 1

            # 每成功跑完一个 eb（returncode==0）就立刻落盘，time limit / 断线也能保留已有结果
            checkpoint()

        print(f"[RDF] Done. Results written to {output_csv} | updated={updated_rows}, added={added_rows}")
    except KeyboardInterrupt:
        checkpoint()
        print("[RDF] interrupted; checkpoint saved.", file=sys.stderr)
        raise
    finally:
        # Slurm 先发 SIGTERM 时有机会进 finally；SIGKILL 仍无法救
        if old_rows:
            try:
                write_rdf_csv(output_csv, fieldnames, old_rows)
            except Exception:
                pass

if __name__ == "__main__":
    main()