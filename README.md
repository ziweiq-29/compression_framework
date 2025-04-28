
In compressor_templates.yaml change the actual path of compressors...

Now only have two compressors, sz3 and qoz. Feel free to replace qoz with sz3 in the commands below.

run single file:
python main.py \
--compressor qoz \
--mode REL \
--sweep 1e-4 1e-3 1e-2 \
--dims "512 512 512" \
--input dataset/NYX/baryon_density.f32


run a specific dataset(e.g. NYX):

python batch_run.py \
--dataset_dir dataset/NYX  \
   --dims "512 512 512" \  
   --compressor qoz  \
   --mode REL  \ 
   --sweep 1e-4 1e-3 1e-2 \
    --results_csv all_results.csv


Adding Qcat(https://github.com/JLiu-1/qcat#) Metrics: 
1. install Qcat into the project.
2. e.g. run the command: 


mode:
support ABS, REL, PSNR, NORM
qcat-evaluators:
support ssim, compareData


Single file:
python main.py \
--compressor sz3 \
--mode REL \
--sweep 1e-4 1e-3 1e-2 \
--dims "512 512 512" \
--input dataset/NYX/baryon_density.f32 \
--enable-qcat \
--datatype f

Dataset:


python batch_run.py \
--dataset_dir dataset/NYX \
--dims "512 512 512" \
--compressor sz3 \
--mode REL \                                                 
--sweep 1e-3 1e-2 \
--enable-qcat \
--datatype f \
--qcat-evaluators "compareData,ssim" 
--results_csv all_results.csv





