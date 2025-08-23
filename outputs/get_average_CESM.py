import pandas as pd
import os
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator, FormatStrFormatter, ScalarFormatter
from matplotlib.ticker import LogLocator, LogFormatter
from matplotlib.ticker import FuncFormatter
plt.rcParams['xtick.labelsize'] = 22
plt.rcParams['ytick.labelsize'] = 22
plt.rcParams['axes.labelsize']  = 22

# 根目录
root_dir = "CESM"
metrics = [
    "psnr", "qcat_local_ssim", "qcat_global_ssim", "pearson",
    "compress_speed(MB/s)", "decompress_speed(MB/s)", "autocorr_lag_1"
]

all_rows = []

color_map = {
    "faz": "#1f77b4",
    "mgard": "#ff7f0e",
    "qoz": "#2ca02c",
    "sperr2d": "#d62728",
    "sz3": "#9467bd",
    "tthresh": "#8c564b",
    "zfp": "#e377c2"
}

marker_map = {
    "faz": "o",
    "mgard": "s",
    "qoz": "^",
    "sperr2d": "D",
    "sz3": "v",
    "tthresh": "X",
    "zfp": "P"
}

metric_map = {
    "psnr": "PSNR(db)",
    "qcat_local_ssim": "Local SSIM",
    "qcat_global_ssim": "Global SSIM",
    "pearson": "Pearson Coefficient",
    "compress_speed(MB/s)": "Compression Speed (MB/s)",
    "decompress_speed(MB/s)": "Decompression Speed (MB/s)",
    "autocorr_lag_1": "Error Autocorrelation"
    
}

# 读取所有结果
for dirpath, dirnames, filenames in os.walk(root_dir):
    for file in filenames:
        if not file.endswith("_results.csv"):
            continue
        compressor = file.replace("_results.csv", "")
        filepath = os.path.join(dirpath, file)

        df = pd.read_csv(filepath)
        df["error_bound"] = pd.to_numeric(df["error_bound"], errors="coerce")
        df["ori_size_MB"] = df["ori_size(B)"] / 1e6
        df["bit_rate"] = 32 / df["compression_ratio"]
        # df["error_bound"] = df["error_bound"].astype(float)
        df["compress_speed(MB/s)"] = df["ori_size_MB"] / df["compress_time(s)"]
        df["decompress_speed(MB/s)"] = df["ori_size_MB"] / df["decompress_time(s)"]
        df = df[['bit_rate','error_bound'] + metrics].copy()

        # 是否在 AC 文件夹中
        is_ac = any(p.lower() == "ac" for p in Path(dirpath).parts)
        if compressor == "faz":
            continue
        if compressor not in {"faz", "qoz"}:
            is_ac = False

        # is_ac = False
        # if compressor in {"faz", "qoz"}:
        #     is_ac = any(p.lower() == "ac" for p in Path(dirpath).parts)

        df["compressor"] = compressor
        df["is_ac"] = is_ac
        df["field"] = os.path.basename(dirpath)
        all_rows.append(df)

if not all_rows:
    raise RuntimeError("未找到任何 *_results.csv！")

df_all = pd.concat(all_rows, ignore_index=True)
df_all["error_bound"] = pd.to_numeric(df_all["error_bound"], errors="coerce")
# 平均数据，按压缩器名 + 是否AC 分组


df_avg = (
    df_all.groupby(["compressor", "is_ac", "error_bound"])[["bit_rate"] + metrics]
    .mean()
    .reset_index()
)
print(df_avg.groupby(["compressor", "is_ac"]).size())

# 保存目录
save_dir = os.path.join(root_dir, "figs")
os.makedirs(save_dir, exist_ok=True)

for metric in metrics:
    x_key = "error_bound" if metric in ["compress_speed(MB/s)", "decompress_speed(MB/s)"] else "bit_rate"

    plt.figure()
    plt.clf()
    for (compressor, is_ac), df_sub in df_avg.groupby(["compressor", "is_ac"]):
        df_sub = df_sub.sort_values(x_key,ascending=False)
        base = compressor
        color = color_map.get(base, None)
        marker = marker_map.get(base, "o")

        if base in ["faz", "qoz"] and is_ac:
            linestyle = "--"
        else:
            linestyle = "-"
            
        if base == "qoz":
            legend_label = "QoZ_AC" if is_ac else "QoZ"
        elif base == "sperr3d" or base == "sperr2d":
            legend_label = "SPERR"
        else:
            legend_label = f"{base.upper()}_AC" if is_ac else base.upper()
        

        plt.plot(
            df_sub[x_key], df_sub[metric],
            marker=marker, color=color, linestyle=linestyle,
            linewidth=2, alpha=0.9, label=legend_label,
            markersize=3, markeredgewidth=0
        )

    if metric in ["compress_speed(MB/s)", "decompress_speed(MB/s)"]:
        plt.xlabel("Error Bound")
    else:
        plt.xlabel("Bit Rate")
    plt.ylabel(metric_map[metric])
    # plt.title(f"{root_dir}: {metric} vs Bit Rate")
    plt.grid(True)
    plt.legend()
    

    ax = plt.gca()

    ax.yaxis.set_major_formatter(ScalarFormatter(useMathText=False))
    ax.ticklabel_format(style="plain", axis="y")  # 禁用科学计数法
    ax.yaxis.get_major_formatter().set_scientific(False)
    ax.yaxis.get_major_formatter().set_useOffset(False)

    if x_key == "error_bound":
        
        ax.set_xscale("log")

    if metric == "qcat_local_ssim":
        ax.set_yscale("linear")  
        ax.yaxis.set_major_locator(MultipleLocator(0.1))
        plt.xlim(0, 4)
        plt.ylim(0.6, 1)
    elif metric == "qcat_global_ssim":
        ax.set_yscale("log")
        ax.set_xlim(0, 0.2)
        ax.set_ylim(0.995, 1.0)
        # ax.set_ylim(1e-4, 1) 
        ax.set_ylabel("Global SSIM")

        from matplotlib.ticker import FuncFormatter, MultipleLocator

        def plain_formatter(x, pos):
            return f"{x:.4f}"  # 保留四位小数

        ax.yaxis.set_major_locator(MultipleLocator(0.001))
        ax.yaxis.set_major_formatter(FuncFormatter(plain_formatter))


    elif metric == "psnr":
        ax.set_yscale("linear") 
        ax.yaxis.set_major_locator(MultipleLocator(20))
        # plt.xlim(0, 8)
        # plt.ylim(44, 130)

    elif metric == "pearson":
        ax.set_yscale("linear")  
        ax.yaxis.set_major_locator(MultipleLocator(0.005))
        plt.xlim(0, 0.2)
        plt.ylim(0.99, 1.001)
    
    elif metric == "compress_speed(MB/s)" or metric == "decompress_speed(MB/s)":
        # 1) 对数轴
        # ax.set_xscale("log")
        ax.set_yscale("log")

        # 2) 先设正常范围，再反向（两者选其一）
        ax.set_xlim(1e-6, 1e-1)   # 正常方向
        ax.set_yscale("log")  
        ax.set_xticks([1e-1,5e-2 ,1e-2, 5e-3, 1e-3, 5e-4 ,1e-4, 5e-5, 1e-5, 5e-6, 1e-6])
        ax.yaxis.set_major_formatter(LogFormatter(labelOnlyBase=False))

        ax.set_xlim(1e-1, 1e-6)
        print("xlim:", ax.get_xlim())
    elif metric == "autocorr_lag_1":
        ax.set_yscale("linear") 
        # plt.xlim(0, 15)
    
    



    # plt.legend(loc="best")
    plt.legend(loc='lower right',fontsize=16)
    plt.tight_layout()
    plt.savefig(os.path.join(save_dir, f"{metric.replace('/', '_')}.pdf"), dpi=200, bbox_inches='tight')
    plt.close()


# import pandas as pd
# import os
# from pathlib import Path
# import matplotlib.pyplot as plt
# from matplotlib.ticker import MultipleLocator, FormatStrFormatter, ScalarFormatter
# from matplotlib.ticker import LogLocator, LogFormatter
# import numpy as np
# from matplotlib.lines import Line2D
# plt.rcParams.update({
#     "font.size": 10,       
#     "axes.labelsize": 20,  
#     "xtick.labelsize": 18,
#     "ytick.labelsize": 18,
#     "legend.fontsize": 22,
# })

# # 根目录
# root_dir = "CESM"
# # metrics = [
# #     "psnr", "qcat_local_ssim", "qcat_global_ssim", "pearson",
# #     "compress_speed(MB/s)", "decompress_speed(MB/s)", "autocorr_lag_1"
# # ]
# metrics = [
#     "psnr", "qcat_local_ssim", "qcat_global_ssim", "pearson",
#      "autocorr_lag_1"
# ]


# all_rows = []

# color_map = {
#     "faz": "#1f77b4",
#     "mgard": "#ff7f0e",
#     "qoz": "#2ca02c",
#     "sperr2d": "#d62728",
#     "sz3": "#9467bd",
#     "tthresh": "#8c564b",
#     "zfp": "#e377c2"
# }

# marker_map = {
#     "faz": "o",
#     "mgard": "s",
#     "qoz": "^",
#     "sperr2d": "D",
#     "sz3": "v",
#     "tthresh": "X",
#     "zfp": "P"
# }

# metric_map = {
#     "psnr": "PSNR(db)",
#     "qcat_local_ssim": "Local SSIM",
#     "qcat_global_ssim": "Global SSIM",
#     "pearson": "Pearson Coefficient",
#     "compress_speed(MB/s)": "Compression Speed (MB/s)",
#     "decompress_speed(MB/s)": "Decompression Speed (MB/s)",
#     "autocorr_lag_1": "Error Autocorrelation"
    
# }

# # 读取所有结果
# for dirpath, dirnames, filenames in os.walk(root_dir):
#     for file in filenames:
#         if not file.endswith("_results.csv"):
#             continue
#         compressor = file.replace("_results.csv", "")
#         filepath = os.path.join(dirpath, file)

#         df = pd.read_csv(filepath)
#         df["error_bound"] = pd.to_numeric(df["error_bound"], errors="coerce")
#         df["ori_size_MB"] = df["ori_size(B)"] / 1e6
#         df["bit_rate"] = 32 / df["compression_ratio"]
#         # df["error_bound"] = df["error_bound"].astype(float)
#         df["compress_speed(MB/s)"] = df["ori_size_MB"] / df["compress_time(s)"]
#         df["decompress_speed(MB/s)"] = df["ori_size_MB"] / df["decompress_time(s)"]
#         df = df[['bit_rate','error_bound'] + metrics].copy()

#         # 是否在 AC 文件夹中
        
#         is_ac = any(p.lower() == "ac" for p in Path(dirpath).parts)
#         if compressor == "faz":
#             continue
#         if compressor not in {"faz", "qoz"}:
#             is_ac = False

#         df["compressor"] = compressor
#         df["is_ac"] = is_ac
#         df["field"] = os.path.basename(dirpath)
#         all_rows.append(df)

# if not all_rows:
#     raise RuntimeError("未找到任何 *_results.csv!")

# df_all = pd.concat(all_rows, ignore_index=True)
# df_all["error_bound"] = pd.to_numeric(df_all["error_bound"], errors="coerce")
# # 平均数据，按压缩器名 + 是否AC 分组
# df_avg = (
#     df_all.groupby(["compressor", "is_ac", "error_bound"])[["bit_rate"] + metrics]
#     .mean()
#     .reset_index()
# )

# # 保存目录
# save_dir = os.path.join(root_dir, "figs")
# os.makedirs(save_dir, exist_ok=True)

# fig, axes = plt.subplots(1, len(metrics), figsize=(20,4)) 
# plt.subplots_adjust(left=0.12, bottom=0.12, right=0.98, top=0.95, wspace=0.3)
# all_handles_labels = {}
# legend_lines = []
# legend_labels = []
# for ax, metric in zip(axes, metrics):
#     x_key = "error_bound" if metric in ["compress_speed(MB/s)", "decompress_speed(MB/s)"] else "bit_rate"
#     ax.tick_params(axis='y', labelrotation=45)
#     for (compressor, is_ac), df_sub in df_avg.groupby(["compressor", "is_ac"]):
#         df_sub = df_sub.sort_values(x_key)

#         base = compressor
#         color = color_map.get(base, None)
#         marker = marker_map.get(base, "o")
#         linestyle = "--" if (base in ["faz","qoz"] and is_ac) else "-"

#         if base == "faz":
#             print("no!!")
#         if base == "qoz":
#             legend_label = "QoZ_AC" if is_ac else "QoZ"
#         # if base == "faz":
#         #       ("no!!")   
            
#         elif base in ["sperr3d","sperr2d"]:
#             print("yes! "+base)
#             legend_label = "SPERR"
        
#         else:
#             legend_label = f"{base.upper()}_AC" if is_ac else base.upper()
        

#         # ============ 关键：过滤 + 防“孤点” + 自相关不画 marker ============
#         x = df_sub[x_key].to_numpy()
#         y = df_sub[metric].to_numpy()

#         mask = np.isfinite(x) & np.isfinite(y)
#         if x_key == "error_bound":      # log x 轴的图要去掉非正数
#             mask &= (x > 0)

#         x, y = x[mask], y[mask]
#         # if len(x) < 2 and metric == "autocorr_lag_1":
#         #     # 少于2个点就跳过（最可靠，彻底不画“孤点”）
#         #     continue

#         this_marker = None if metric == "autocorr_lag_1" else marker  # 自相关不画点
#         ax.plot(
#             x, y,
#             linestyle=linestyle, color=color,
#             marker=this_marker, markersize=3, markeredgewidth=0,
#             linewidth=2, alpha=0.9,
#             label="_nolegend_"  # 不把真实线条加入 legend
#         )

#         # 只在第一次出现时构造一次代理句柄（legend 用它，不会往轴里画任何点）
#         if not any(lbl == legend_label for lbl in legend_labels):
#             legend_lines.append(Line2D([], [], color=color, linestyle=linestyle,
#                                        marker=marker if this_marker is not None else None,
#                                        linewidth=2, markersize=6))
#             legend_labels.append(legend_label)

#     if metric in ["compress_speed(MB/s)", "decompress_speed(MB/s)"]:
#         ax.set_xlabel("Error Bound")
#     else:
#         ax.set_xlabel("Bit Rate")
#     ax.set_ylabel(metric_map[metric])
#     # plt.title(f"{root_dir}: {metric} vs Bit Rate")
#     ax.grid(True)
#     # plt.legend()
    

#     # ax = plt.gca()

#     ax.yaxis.set_major_formatter(ScalarFormatter(useMathText=False))
#     ax.ticklabel_format(style="plain", axis="y")  # 禁用科学计数法
#     ax.yaxis.get_major_formatter().set_scientific(False)
#     ax.yaxis.get_major_formatter().set_useOffset(False)

#     if x_key == "error_bound":
        
#         ax.set_xscale("log")
#     else:
#         ax.set_xscale("linear")

#     if metric == "qcat_local_ssim":
#         ax.set_yscale("linear")  
#         ax.yaxis.set_major_locator(MultipleLocator(0.1))
#         ax.set_xlim(0, 4)
#         ax.set_ylim(0.6, 1)
#     elif metric == "qcat_global_ssim":
#         ax.set_yscale("log")
#         ax.set_xlim(0, 0.2)
#         ax.set_ylim(0.995, 1.0)
#         ax.set_ylabel("Global SSIM")

#         from matplotlib.ticker import FuncFormatter, MultipleLocator

#         def plain_formatter(x, pos):
#             return f"{x:.3f}"  # 保留四位小数

#         ax.yaxis.set_major_locator(MultipleLocator(0.001))
#         ax.yaxis.set_major_formatter(FuncFormatter(plain_formatter))


#     elif metric == "psnr":
#         ax.set_yscale("linear") 
#         ax.yaxis.set_major_locator(MultipleLocator(20))
#         ax.set_xlim(0, 8)
#         ax.set_ylim(44, 130)

#     elif metric == "pearson":
#         ax.set_yscale("linear")  
#         ax.yaxis.set_major_locator(MultipleLocator(0.005))
#         ax.set_xlim(0, 0.2)
#         ax.set_ylim(0.99, 1.001)
    


#     elif metric == "autocorr_lag_1":
#         ax.set_yscale("linear") 
#         ax.set_xlim(0, 15)
        
#     elif metric == "compress_speed(MB/s)" or metric == "decompress_speed(MB/s)":
#         ax.set_yscale("log")  
#         ax.set_xticks([1e-1,5e-2 ,1e-2, 5e-3, 1e-3, 5e-4 ,1e-4, 5e-5, 1e-5, 5e-6, 1e-6])
#         ax.yaxis.set_major_formatter(LogFormatter(labelOnlyBase=False))
#         ax.xaxis.set_major_formatter(LogFormatter(labelOnlyBase=False))
    
    

# handles = list(all_handles_labels.values())
# labels = list(all_handles_labels.keys())

# # fig.legend(handles, labels,
# #            loc="lower center",         # 底部
# #            bbox_to_anchor=(0.5, -0.08), # 稍微往下挪一点
# #            ncol=4,                     # 每行放几个 legend，可以调大/调小
# #            fontsize=16)
# fig.legend(legend_lines, legend_labels,
#            loc="lower center", bbox_to_anchor=(0.5, -0.08),
#            ncol=len(legend_labels), fontsize=16)
# plt.tight_layout(rect=[0, 0.05, 1, 1])  # 留出底部空间
# plt.savefig(os.path.join(save_dir, "combined.pdf"), dpi=200, bbox_inches='tight')
# plt.close()






