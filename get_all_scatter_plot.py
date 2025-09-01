import os
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

def scan_and_plot_all_results(
    outputs_dir="outputs",
    out_dir="outputs/figs_all",
    target_datasets=None,     # 限定 datasets，如 ["NYX", "CESM"]
    target_compressors=None,  # ✅ 限定 compressors，如 ["SZ3", "QoZ"]
    metrics=("mean_error_norm", "std_error_norm","nrmse","error_std_norm")
):
    os.makedirs(out_dir, exist_ok=True)
    all_rows = []
    
    for dirpath, _, filenames in os.walk(outputs_dir):
        # print("正在扫描目录:", dirpath)  # ✅ 加这个
        if "log10" in dirpath:
            # print(f"[SKIP] Skipping {dirpath} because it contains 'log10'")
            continue
            
        # print(dirpath)
        parts = Path(dirpath).parts
        # if "AC" in parts:
        #     ac_enabled = True
        # else:
        #     ac_enabled = False
        
        ac_enabled = False

        # 提取 dataset 和 field
        if len(parts) < 3:
            continue  # 跳过结构不完整的路径

        dataset = parts[1]

        if  ac_enabled == True:
            if "AC" not in parts:
                continue
            ac_index = parts.index("AC")
            if ac_index + 1 >= len(parts):
                continue  # AC 后没有 field，跳过
            field = parts[ac_index + 1]
        else:
            field = parts[2]
        

        if target_datasets and dataset not in target_datasets:
            print(dataset,field)
            continue
            
        # target_compressor_name = "qoz" 
        for file in filenames:

            # print(file, filenames)
            if not file.endswith("_results.csv") :
                continue

            try:
                filepath = os.path.join(dirpath, file)
                # print("[DEBUG] filepath:", filepath)
                # print("[DEBUG] parts:", Path(filepath).parts)
                df = pd.read_csv(filepath)

                # 计算指标列
                df["error_bound"] = pd.to_numeric(df["error_bound"], errors="coerce")
                df["mean_error_norm"] = (df["dec_mean"] - df["ori_mean"]).abs() / df["range"]
                df["std_error_norm"]  = (df["dec_std"]  - df["ori_std"]).abs()  / df["range"]
                df["error_std_norm"] = df["err_std"] / df["range"]
                df["field"] = field
                df["dataset"] = dataset
                comp_name = file.replace("_results.csv", "")
                if comp_name in ["sperr2d", "sperr3d"]:
                    comp_name = "sperr"
                df["compressor"] = comp_name
                # print(df)
                all_rows.append(df)

            except Exception as e:
                print(f"[WARN] 读取失败: {filepath}: {e}")

    if not all_rows:
        print("没有找到任何结果文件或解析失败")
        return

    df_all = pd.concat(all_rows, ignore_index=True)

    compressors = df_all["compressor"].unique().tolist()
    if target_compressors:
        compressors = [c for c in compressors if c in target_compressors]
    
    



    created = 0
    for comp in compressors:
        df_comp = df_all[df_all["compressor"] == comp]

        for metric in metrics:
            plt.figure()
            # plt.scatter(df_comp["error_bound"], df_comp[metric], alpha=0.7)
            for dataset, df_group in df_comp.groupby("dataset"):
                plt.scatter(df_group["error_bound"], df_group[metric], label=dataset, alpha=0.7)
            plt.xscale("log")
            plt.yscale("log")
            plt.xlabel("error_bound")
            plt.ylabel(metric)
            plt.title(f"{comp} - {metric} vs error_bound(all datasets)")
            plt.grid(True, linestyle="--", alpha=0.6)
            plt.legend(title="Dataset")
            plt.tight_layout()

            out_path = os.path.join(out_dir, f"{comp}_{metric}_scatter.png")
            plt.savefig(out_path, dpi=150)
            plt.close()
            created += 1

    print(f"✅ 共生成 {created} 张图，保存在 {out_dir}/")


if __name__ == "__main__":
    scan_and_plot_all_results(
        outputs_dir="outputs",
        out_dir="outputs/figs_all/sperr",
        target_datasets=["NYX", "CESM","100x500x500","288x115x69x69","SDRBENCH-Miranda-f32","SDRBENCH-SCALE_98x1200x1200"],         # ✅ 控制 dataset
        target_compressors=["sperr"],       # ✅ 控制 compressor
        metrics=["mean_error_norm", "std_error_norm","nrmse","error_std_norm"]
    )
