
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
