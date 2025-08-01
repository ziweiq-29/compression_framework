import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import glob
import os


# sns.set(style="whitegrid")

import os, glob

file_dir = os.path.join(".", "NYX", "baryon_density_log10_dat")
pattern = os.path.join(file_dir, "*_results.csv")



csv_files = glob.glob(pattern)


if not csv_files:
    print("no files found!")
    exit()


all_dfs = []
for file in csv_files:
    df = pd.read_csv(file)
    compressor = os.path.splitext(os.path.basename(file))[0].replace("_results", "")
    df["compressor name"] = compressor  
    all_dfs.append(df)

df_all = pd.concat(all_dfs, ignore_index=True)

# speed: MB/s
df_all["ori_size_MB"] = df_all["ori_size(B)"] / (1024 * 1024)
df_all["compress_speed_MBps"] = df_all["ori_size_MB"] / df_all["compress_time(s)"]
df_all["decompress_speed_MBps"] = df_all["ori_size_MB"] / df_all["decompress_time(s)"]



output_dir1 = "plots1"
os.makedirs(output_dir1, exist_ok=True)
# compression-speed
plt.figure(figsize=(10, 6))
sns.lineplot(data=df_all, x="error_bound", y="compress_speed_MBps", hue="compressor name", marker="o")
plt.title("Compression Speed vs Error Bound")
plt.xlabel("Error Bound")
plt.ylabel("Compression Speed (MB/s)")
plt.xscale("log")
plt.yscale("log")
# plt.tight_layout()
plt.legend(loc="upper left", bbox_to_anchor=(1.0, 1.0), borderaxespad=0.)
plt.title("Compression Speed vs Error Bound on "+file_dir)
save_path = os.path.join(output_dir1,"compression.png")
plt.savefig(save_path, dpi=300,bbox_inches='tight')
plt.show()

# # decompression-speed
plt.figure(figsize=(10, 6))
sns.lineplot(data=df_all, x="error_bound", y="decompress_speed_MBps", hue="compressor name", marker="o")
plt.title("Decompression Speed vs Error Bound")
plt.xlabel("Error Bound")
plt.ylabel("Decompression Speed (MB/s)")
plt.xscale("log")
plt.yscale("log")
# plt.tight_layout()
plt.legend(loc="upper left", bbox_to_anchor=(1.0, 1.0), borderaxespad=0.)
plt.title("Dompression Speed vs Error Bound on "+file_dir)
save_path = os.path.join(output_dir1,"dcompression.png")
plt.savefig(save_path, dpi=300,bbox_inches='tight')
plt.show()



# --- bit rate vs metrics ---

output_dir2 = "plots2"
os.makedirs(output_dir2, exist_ok=True)
element_size = 4
num_elements = df_all["ori_size(B)"].iloc[0] / element_size
df_all["bit_rate"] = (df_all["ori_size(B)"] * 8 / df_all["compression_ratio"]) / num_elements

metrics = [
    ("psnr", "PSNR"),
    ("qcat_local_ssim", "Local SSIM"),
    ("qcat_global_ssim", "Global SSIM"),
    ("autocorr_lag_1", "Autocorr (lag=1)"),
    ("pearson", "Pearson Correlation")
]

for metric, label in metrics:
    plt.figure(figsize=(8, 5))
    sns.lineplot(data=df_all, x="bit_rate", y=metric, hue="compressor name", marker="o")
    plt.title(f"{label} vs Bit Rate on "+file_dir)
    plt.xlabel("Bit Rate (bits/value)")
    plt.ylabel(label)
    plt.tight_layout()
    plt.xscale("log")
    plt.yscale("log")
    save_path = os.path.join(output_dir2, f"{metric}_vs_bitrate.png")
    plt.savefig(save_path, dpi=300)
    plt.show()

print(df_all["compressor name"].unique())

output_dir3 = "plots3"
os.makedirs(output_dir3, exist_ok=True)
# df_all["normalized_eb"] = df_all["error_bound"] / df_all["range"]
df_all["normalized_eb"] = df_all["error_bound"] 


df_all["rmse"] = df_all["nrmse"] * df_all["range"]

df_all["mean_err"] = abs(df_all["dec_mean"] - df_all["ori_mean"])
df_all["nmean_err"] = df_all["mean_err"] / df_all["range"] 


df_all["std_err"] = abs(df_all["dec_std"] - df_all["ori_std"])
df_all["nstd_err"] = df_all["std_err"] / df_all["range"]

sns.set(style="whitegrid")


metrics = [
    ("nmean_err", "Normalized Mean Error"),
    ("nstd_err", "Normalized Std Error"),
    ("err_std", "Error Std"),
    ("nrmse", "Normalized RMSE"),
]

for metric, label in metrics:
    if metric not in df_all.columns:
        print(f"[WARN] {metric} not found, skipping...")
        continue

    plt.figure(figsize=(8,5))
    sns.lineplot(data=df_all, x="normalized_eb", y=metric, hue="compressor name", marker="o")
    plt.xscale("log")
    plt.yscale("log")
    plt.title(f"{label} vs Normalized Error Bound on "+file_dir)
    plt.xlabel("Normalized Error Bound")
    plt.ylabel(label)
    # plt.tight_layout()
    plt.legend(loc="upper left", bbox_to_anchor=(1.0, 1.0), borderaxespad=0.)
    save_path = os.path.join(output_dir3, f"{metric}_vs_bitrate.png")
    plt.savefig(save_path, dpi=300,bbox_inches='tight')
    plt.show()

