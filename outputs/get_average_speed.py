# import pandas as pd
# import os
# from pathlib import Path
# import matplotlib.pyplot as plt
# from matplotlib.ticker import LogFormatter, FuncFormatter
# from matplotlib.ticker import LogLocator, LogFormatterMathtext

# plt.rcParams.update({
#     "font.size": 28,       
#     "axes.labelsize": 20,  
#     "xtick.labelsize": 20,
#     "ytick.labelsize": 20,
#     "legend.fontsize": 22,
# })

# # 多个数据集根目录
# root_dirs = ["NYX","100x500x500","288x115x68x69","CESM","SDRBENCH-Miranda-f32","SDRBENCH-SCALE_98x1200x1200"]

# # 可视化配置
# color_map = {
#     "faz": "#1f77b4",
#     "mgard": "#ff7f0e",
#     "qoz": "#2ca02c",
#     "sperr3d": "#d62728",
#     "sz3": "#9467bd",
#     "tthresh": "#8c564b",
#     "zfp": "#e377c2"
# }
# marker_map = {
#     "faz": "o", "mgard": "s", "qoz": "^", "sperr3d": "D",
#     "sz3": "v", "tthresh": "X", "zfp": "P"
# }

# all_rows = []

# # 遍历所有目录
# for root_dir in root_dirs:
#     for dirpath, dirnames, filenames in os.walk(root_dir):
#         if "log10" in dirpath:
#             continue
#         for file in filenames:
#             if not file.lower().endswith("_results.csv"):
#                 continue
#             raw_compressor = file.replace("_results.csv", "").lower()
#             dir_parts = [p.lower() for p in Path(dirpath).parts]
#             is_ac = any(part == "ac" for part in dir_parts)

#             if raw_compressor.startswith("faz"):
#                 compressor = "faz"
#             elif raw_compressor.startswith("qoz"):
#                 compressor = "qoz"
#             else:
#                 compressor = raw_compressor
#                 is_ac = False  # 非 FAZ/QOZ 永远不能是 A

#             filepath = os.path.join(dirpath, file)

#             try:
#                 df = pd.read_csv(filepath)
#             except pd.errors.ParserError as e:
#                 print(f"[Warning] Failed to parse {filepath}: {e}")
#                 continue 

#             df["error_bound"] = pd.to_numeric(df["error_bound"], errors="coerce")
#             df["ori_size_MB"] = df["ori_size(B)"] / 1e6
#             df["compress_time(s)"] = pd.to_numeric(df["compress_time(s)"], errors="coerce")
#             df["compress_speed(MB/s)"] = df["ori_size_MB"] / df["compress_time(s)"]
#             if compressor in ["faz", "qoz"]:
#                 dir_parts = [p.lower() for p in Path(dirpath).parts]
#                 is_ac = any(part == "ac" for part in dir_parts)

#             df["compressor"] = compressor
#             df["is_ac"] = is_ac
#             df["field"] = os.path.basename(dirpath)
#             all_rows.append(df[["compressor", "is_ac", "error_bound", "ori_size_MB", "compress_time(s)"]])


# # 合并数据
# if not all_rows:
#     raise RuntimeError("未找到任何 *_results.csv 文件")
# df_all = pd.concat(all_rows, ignore_index=True)

# # 聚合：平均速度 = 所有数据大小总和 / 压缩总时间


# agg_speed = (
#     df_all.groupby(["compressor", "is_ac", "error_bound"])
#     .agg(
#         total_size_MB=("ori_size_MB", "sum"),
#         total_compress_time=("compress_time(s)", "sum")
#     )
#     .reset_index()
# )
# agg_speed["compress_speed(MB/s)"] = agg_speed["total_size_MB"] / agg_speed["total_compress_time"]
# print(agg_speed[agg_speed["compressor"] == "faz"].groupby("is_ac").size())
# # 保存图像目录
# save_dir = "figs_all_datasets"
# os.makedirs(save_dir, exist_ok=True)

# # 绘图
# plt.figure(figsize=(15,10))
# plt.clf()

# for (compressor, is_ac), df_sub in agg_speed.groupby(["compressor", "is_ac"]):
#     df_sub = df_sub.sort_values("error_bound", ascending=False)
#     base = compressor
#     color = color_map.get(base, None)
#     marker = marker_map.get(base, "o")
#     # linestyle = "--" if base in ["faz", "qoz"] and is_ac else "-"

    


#     if base == "qoz":
#         legend_label = "QoZ_AC" if is_ac else "QoZ"
#     elif base == "sperr3d" or base == "sperr2d":
#         legend_label = "SPERR"
#     else:
#         legend_label = f"{base.upper()}_AC" if is_ac else base.upper()
    
#         # 重新判断 linestyle（用 label 而不是 base）
#     if legend_label.endswith("_AC"):
#         linestyle = "--"
#     else:
#         linestyle = "-"


#     plt.plot(
#         df_sub["error_bound"], df_sub["compress_speed(MB/s)"],
#         marker=marker, color=color, linestyle=linestyle,
#         linewidth=2, alpha=0.9, label=legend_label,
#         markersize=4, markeredgewidth=0
#     )

# # 坐标轴设置
# ax = plt.gca()
# ax.set_yscale("log")
# ax.set_xscale("log")
# ax.set_xlim(1e-1, 1e-6) 

# ax.xaxis.set_major_locator(LogLocator(base=10.0, numticks=12))
# ax.xaxis.set_major_formatter(LogFormatterMathtext())



# plt.xlabel("Error Bound",fontsize=38)
# plt.ylabel("Compression Speed (MB/s)",fontsize=38)
# plt.grid(True, which="both", linestyle="--", linewidth=0.5)


# handles, labels = plt.gca().get_legend_handles_labels()
# by_label = dict(zip(labels, handles))
# plt.legend(    by_label.values(),  
#     by_label.keys(),  loc='upper right',ncols=1, fontsize=20)
# plt.tight_layout()
# plt.savefig(os.path.join(save_dir, "get_average_speed.pdf"), dpi=200, bbox_inches='tight')
# plt.close()



import pandas as pd
import os
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.ticker import LogLocator, LogFormatterMathtext

plt.rcParams.update({
    "font.size": 28,       
    "axes.labelsize": 20,  
    "xtick.labelsize": 20,
    "ytick.labelsize": 20,
    "legend.fontsize": 22,
})

root_dirs = [
    "NYX", "100x500x500", "288x115x68x69",
    "CESM", "SDRBENCH-Miranda-f32", "SDRBENCH-SCALE_98x1200x1200"
]

color_map = {
    "faz": "#1f77b4", "mgard": "#ff7f0e", "qoz": "#2ca02c",
    "sperr": "#d62728", "sz3": "#9467bd",
    "tthresh": "#8c564b", "zfp": "#e377c2"
}
marker_map = {
    "faz": "o", "mgard": "s", "qoz": "^", "sperr": "D",
    "sz3": "v", "tthresh": "X", "zfp": "P"
}

all_rows = []

for root_dir in root_dirs:
    for dirpath, _, filenames in os.walk(root_dir):
        if "log10" in dirpath.lower():
            continue
        for file in filenames:
            if not file.lower().endswith("_results.csv"):
                continue

            raw_compressor = file.replace("_results.csv", "").lower()
            path_parts = [p.lower() for p in Path(dirpath).parts]
            is_ac = (raw_compressor in ["faz", "qoz"]) and ("ac" in path_parts)

            # Debug 输出：路径和是否识别成 AC
            if raw_compressor.startswith("faz"):
                print(f"[DEBUG] FAZ file: {os.path.join(dirpath, file)} → is_ac={is_ac}")

            if raw_compressor.startswith("faz"):
                compressor = "faz"
            elif raw_compressor.startswith("qoz"):
                compressor = "qoz"
            elif raw_compressor.startswith("sperr"):
                compressor = "sperr"
            else:
                compressor = raw_compressor

            filepath = os.path.join(dirpath, file)
            try:
                df = pd.read_csv(filepath)
            except pd.errors.ParserError as e:
                print(f"[Warning] Failed to parse {filepath}: {e}")
                continue

            df["error_bound"] = pd.to_numeric(df["error_bound"], errors="coerce")
            df["ori_size_MB"] = df["ori_size(B)"] / 1e6
            df["compress_time(s)"] = pd.to_numeric(df["compress_time(s)"], errors="coerce")
            df["compress_speed(MB/s)"] = df["ori_size_MB"] / df["compress_time(s)"]

            df["compressor"] = compressor
            df["is_ac"] = is_ac
            df["field"] = os.path.basename(dirpath)

            all_rows.append(df[["compressor", "is_ac", "error_bound", "ori_size_MB", "compress_time(s)"]])

if not all_rows:
    raise RuntimeError("❌ 未找到任何 *_results.csv 文件")
df_all = pd.concat(all_rows, ignore_index=True)
group_counts = df_all.groupby(["compressor", "is_ac"]).size().reset_index(name="count")

print("⚠️ 当前所有 (compressor, is_ac) 组合：")
print(group_counts)

# 去重：防止同一个 compressor + is_ac 重复绘图
df_all.drop_duplicates(subset=["compressor", "is_ac", "error_bound"], keep="last", inplace=True)

# 聚合压缩速度
agg_speed = (
    df_all.groupby(["compressor", "is_ac", "error_bound"])
    .agg(
        total_size_MB=("ori_size_MB", "sum"),
        total_compress_time=("compress_time(s)", "sum")
    )
    .reset_index()
)
agg_speed["compress_speed(MB/s)"] = agg_speed["total_size_MB"] / agg_speed["total_compress_time"]

# ✅ 打印将被绘图的 legend 标签（帮助你确认有没有重复）
print("\n🎯 将绘制的压缩器曲线：")
for (compressor, is_ac), _ in agg_speed.groupby(["compressor", "is_ac"]):
    print(f"  → {compressor.upper()} | is_ac={is_ac}")

save_dir = "figs_all_datasets"
os.makedirs(save_dir, exist_ok=True)

plt.figure(figsize=(15, 10))
plt.clf()
legend_labels = set()
for (compressor, is_ac), df_sub in agg_speed.groupby(["compressor", "is_ac"]):
    df_sub = df_sub.sort_values("error_bound", ascending=False)
    base = compressor
    color = color_map.get(base, None)
    marker = marker_map.get(base, "o")

    if base == "qoz":
        legend_label = "QoZ_AC" if is_ac else "QoZ"
    elif base in ["sperr3d", "sperr2d"]:
        legend_label = "SPERR"
    else:
        legend_label = f"{base.upper()}_AC" if is_ac else base.upper()

    linestyle = "--" if legend_label.endswith("_AC") else "-"
    print("\n✅ 实际参与绘图的压缩器组合：")
    combos = agg_speed.groupby(["compressor", "is_ac"]).size().reset_index().rename(columns={0: "count"})
    print(combos.to_string(index=False))
    print("✅ 总共曲线数 =", len(combos))
    plt.plot(
        df_sub["error_bound"], df_sub["compress_speed(MB/s)"],
        marker=marker, color=color, linestyle=linestyle,
        linewidth=2, alpha=0.9, label=legend_label,
        markersize=4, markeredgewidth=0
    )
    legend_labels.add(legend_label)
    
    print("✅ 最终 legend label 有几条：", len(legend_labels))
    print("👉 它们是：", legend_labels)

ax = plt.gca()
ax.set_yscale("log")
ax.set_xscale("log")
ax.set_xlim(1e-1, 1e-6)

ax.xaxis.set_major_locator(LogLocator(base=10.0, numticks=12))
ax.xaxis.set_major_formatter(LogFormatterMathtext())

plt.xlabel("Error Bound", fontsize=38)
plt.ylabel("Compression Speed (MB/s)", fontsize=38)
plt.grid(True, which="both", linestyle="--", linewidth=0.5)

# 去重 legend
handles, labels = plt.gca().get_legend_handles_labels()
by_label = dict(zip(labels, handles))
plt.legend(by_label.values(), by_label.keys(), loc='upper right', ncols=1, fontsize=20)
plt.tight_layout()
plt.savefig(os.path.join(save_dir, "get_average_speed.pdf"), dpi=200, bbox_inches='tight')
plt.close()
