import os
import pandas as pd
import matplotlib.pyplot as plt

# ================= paths =================
BASE_DIR = "/home/ziweiq2/compression_framework/outputs/HALO/NYX/baryon_density_f32"
PLOT_DIR = "/home/ziweiq2/compression_framework/outputs/HALO/NYX/plots"

RESULTS_CSV = os.path.join(BASE_DIR, "sz3_results.csv")
HALO_CSV = os.path.join(BASE_DIR, "sz3_halo.csv")

os.makedirs(PLOT_DIR, exist_ok=True)

# ================= load =================
df_results = pd.read_csv(RESULTS_CSV)
df_halo = pd.read_csv(HALO_CSV)

print("results columns:", df_results.columns.tolist())
print("halo columns:", df_halo.columns.tolist())

# ================= merge =================
# 使用你新加的 compressor_name
merge_keys = ["compressor name", "error_bound"]

df = pd.merge(
    df_results,
    df_halo,
    on=merge_keys,
    how="inner"
)

print(f"Merged rows: {len(df)}")

# ================= scatter plot =================
plt.figure(figsize=(7, 6))

for comp, g in df.groupby("compressor name"):
    plt.scatter(
        g["qcat_global_ssim"],
        g["max"],
        label=comp,
        alpha=0.7
    )

plt.xlabel("qcat_global_ssim")
plt.ylabel("max")
plt.title("qcat_global_ssim vs p999 (merged by compressor + error bound)")
plt.legend()
plt.grid(True)
plt.tight_layout()

out_path = os.path.join(PLOT_DIR, "ssim_vs_max_scatter.png")
plt.savefig(out_path, dpi=300)
plt.close()

print(f"Saved plot to {out_path}")
