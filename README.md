
In compressor_templates.yaml change the actual path of compressors



run:
python main.py \
  --compressor qoz \
  --mode REL \
  --sweep 1e-4 1e-3 1e-2 \
  --dims "512 512 512" \
  --input dataset/NYX/baryon_density.f32
