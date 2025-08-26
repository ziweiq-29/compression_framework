import pandas as pd
import os
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.ticker import LogFormatter, FuncFormatter
from matplotlib.ticker import LogLocator, LogFormatterMathtext

plt.rcParams['xtick.labelsize'] = 22
plt.rcParams['ytick.labelsize'] = 22
plt.rcParams['axes.labelsize']  = 18

# 多个数据集根目录
root_dirs = ["NYX","100x500x500","288x115x68x69","CESM","SDRBENCH-Miranda-f32","SDRBENCH-SCALE_98x1200x1200"]

# 可视化配置
color_map = {
    "faz": "#1f77b4",
    "mgard": "#ff7f0e",
    "qoz": "#2ca02c",
    "sperr3d": "#d62728",
    "sz3": "#9467bd",
    "tthresh": "#8c564b",
    "zfp": "#e377c2"
}
marker_map = {
    "faz": "o", "mgard": "s", "qoz": "^", "sperr3d": "D",
    "sz3": "v", "tthresh": "X", "zfp": "P"
}

all_rows = []

# 遍历所有目录
for root_dir in root_dirs:
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if "log10" in dirpath:
            continue
        for file in filenames:
            if not file.endswith("_results.csv"):
                continue

            compressor = file.replace("_results.csv", "")
            filepath = os.path.join(dirpath, file)
            df = pd.read_csv(filepath)

            df["error_bound"] = pd.to_numeric(df["error_bound"], errors="coerce")
            df["ori_size_MB"] = df["ori_size(B)"] / 1e6
            df["compress_time(s)"] = pd.to_numeric(df["compress_time(s)"], errors="coerce")
            df["compress_speed(MB/s)"] = df["ori_size_MB"] / df["compress_time(s)"]

            is_ac = any(p.lower() == "ac" for p in Path(dirpath).parts)
            df["compressor"] = compressor
            df["is_ac"] = is_ac
            df["field"] = os.path.basename(dirpath)
            all_rows.append(df[["compressor", "is_ac", "error_bound", "ori_size_MB", "compress_time(s)"]])

# 合并数据
if not all_rows:
    raise RuntimeError("未找到任何 *_results.csv 文件")
df_all = pd.concat(all_rows, ignore_index=True)

# 聚合：平均速度 = 所有数据大小总和 / 压缩总时间
agg_speed = (
    df_all.groupby(["compressor", "is_ac", "error_bound"])
    .agg(
        total_size_MB=("ori_size_MB", "sum"),
        total_compress_time=("compress_time(s)", "sum")
    )
    .reset_index()
)
agg_speed["compress_speed(MB/s)"] = agg_speed["total_size_MB"] / agg_speed["total_compress_time"]

# 保存图像目录
save_dir = "figs_all_datasets"
os.makedirs(save_dir, exist_ok=True)

# 绘图
plt.figure()
plt.clf()

for (compressor, is_ac), df_sub in agg_speed.groupby(["compressor", "is_ac"]):
    df_sub = df_sub.sort_values("error_bound", ascending=False)
    base = compressor
    color = color_map.get(base, None)
    marker = marker_map.get(base, "o")
    linestyle = "--" if base in ["faz", "qoz"] and is_ac else "-"

    


    if base == "qoz":
        legend_label = "QoZ_AC" if is_ac else "QoZ"
    elif base == "sperr3d" or base == "sperr2d":
        legend_label = "SPERR"
    else:
        legend_label = f"{base.upper()}_AC" if is_ac else base.upper()
    plt.plot(
        df_sub["error_bound"], df_sub["compress_speed(MB/s)"],
        marker=marker, color=color, linestyle=linestyle,
        linewidth=2, alpha=0.9, label=legend_label,
        markersize=4, markeredgewidth=0
    )

# 坐标轴设置
ax = plt.gca()
ax.set_yscale("log")
ax.set_xscale("log")
ax.set_xlim(1e-1, 1e-6) 
# xticks = [1e-1, 5e-2, 1e-2, 5e-3, 1e-3, 5e-4, 1e-4, 5e-5, 1e-5, 5e-6, 1e-6]
# xtick_labels = [f"{x:.0e}" for x in xticks]
# ax.set_xticks(xticks)
# ax.set_xticklabels(xtick_labels, rotation=0)
ax.xaxis.set_major_locator(LogLocator(base=10.0, numticks=12))
ax.xaxis.set_major_formatter(LogFormatterMathtext())



plt.xlabel("Error Bound")
plt.ylabel("Compression Speed (MB/s)")
plt.grid(True, which="both", linestyle="--", linewidth=0.5)


handles, labels = plt.gca().get_legend_handles_labels()
by_label = dict(zip(labels, handles))
plt.legend(    by_label.values(),  
    by_label.keys(),  loc='upper right',ncols=1, fontsize=5)
plt.tight_layout()
plt.savefig(os.path.join(save_dir, "get_average_speed.pdf"), dpi=200, bbox_inches='tight')
plt.close()
