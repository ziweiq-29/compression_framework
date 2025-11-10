import os
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import re

def scan_error_files(root="outputs/error_samples"):

    results = []
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            if not f.startswith("errors_") or not f.endswith(".npy"):
                continue
            m = re.search(r"errors_([0-9eE\.-]+)\.npy", f)
            if not m:
                continue
            error_bound = float(m.group(1))
            parts = Path(dirpath).parts
            if len(parts) < 4:
                continue
            dataset = parts[1]
            field = parts[2]
            compressor = parts[3] if len(parts) > 3 else "unknown"
            results.append((compressor, dataset, field, error_bound, os.path.join(dirpath, f)))
    return results



def plot_all_distributions(error_list, out_dir="outputs/error_samples/figs_error_analysis"):
    """针对每个 compressor 汇总绘图"""
    os.makedirs(out_dir, exist_ok=True)
    grouped = {}
    for comp, dataset, field, eb, path in error_list:
        grouped.setdefault(comp, []).append((eb, path))

    for comp, files in grouped.items():
        files.sort(key=lambda x: x[0])
        colors = sns.color_palette("coolwarm", len(files))
        plt.figure(figsize=(7, 5))
        for i, (eb, path) in enumerate(files):
            errors = np.load(path)
            # errors=errors/eb
            print(np.min(errors), np.max(errors))
            # sns.kdeplot(errors, fill=True, alpha=0.4, color=colors[i], label=f"error_bound={eb:.0e}")
            sns.histplot(
    errors, 
    bins=50, 
    stat='density', 
    color=colors[i], 
    alpha=0.4, 
    label=f"error_bound={eb:.0e}",
    edgecolor=None
)

            # sns.histplot(errors, bins=100, stat='density', color=colors[i], alpha=0.3)

            # sns.histplot(errors, bins=200, stat='density', element='step', fill=True, alpha=0.3, color=colors[i], label=f"error_bound={eb:.0e}")
            plt.xlim(-1, 1)

            # 自定义横轴刻度标签
            plt.xticks(
                # [-eb, -eb/2, 0, eb/2, eb],
                [-1, -0.5, 0, 0.5, 1],
                [r"$-\varepsilon$", r"$-\varepsilon/2$", "0", r"$+\varepsilon/2$", r"$+\varepsilon$"]
)

        plt.xlabel("Error value")
        plt.ylabel("Density")
        plt.title(f"True Error Distributions for {comp}")
        # plt.legend()
        
        plt.legend(
    title="Error bound",
    loc="center left",             # 图例放在图的左中位置，但锚点偏到图外
    bbox_to_anchor=(1.05, 0.5),    # (x=1.05 表示略偏出右边界)
    frameon=False
)
        plt.grid(True, linestyle="--", alpha=0.5)
        plt.tight_layout()
        out_path = os.path.join(out_dir, f"{comp}_error_distributions.png")
        plt.savefig(out_path, dpi=200)
        plt.close()
        print(f"[INFO] Saved {out_path}")

    print(f"✅ 生成 {len(grouped)} 张分布图，保存在 {out_dir}/")






for f in os.listdir("outputs/error_samples/NYX/baryon_density_f32"):
    if f.endswith(".npy"):
        err = np.load(os.path.join("outputs/error_samples/NYX/baryon_density_f32", f))
        print(f"{f:25s} min={err.min():.3e}, max={err.max():.3e}, mean={err.mean():.3e}, std={err.std():.3e}")

if __name__ == "__main__":
    errors = scan_error_files("outputs")
    print(f"[INFO] 找到 {len(errors)} 个 error 文件")
    plot_all_distributions(errors)
