"""Visualize V-JEPA 2.1 dense features for a single image as PCA-RGB."""
import sys
import numpy as np
import torch
from PIL import Image

data = torch.load(sys.argv[1], weights_only=False)
features = data["features"].squeeze(0).float().numpy()  # (N_tokens, 1024)
input_path = data["input"]

# 384px / patch_size 16 = 24x24 = 576 spatial tokens per temporal step
n_tokens = features.shape[0]
spatial_h, spatial_w = 24, 24
n_spatial = spatial_h * spatial_w  # 576
n_temporal = n_tokens // n_spatial
print(f"Tokens: {n_tokens} = {n_temporal} temporal x {spatial_h}x{spatial_w} spatial")

# Take features from one temporal step (for images they're all identical)
frame_features = features[:n_spatial]  # (576, 1024)

# PCA to 3 channels
mean = frame_features.mean(axis=0)
centered = frame_features - mean
cov = centered.T @ centered / len(centered)
eigvals, eigvecs = np.linalg.eigh(cov)
top3 = eigvecs[:, -3:][:, ::-1]
proj = centered @ top3  # (576, 3)

for c in range(3):
    lo, hi = proj[:, c].min(), proj[:, c].max()
    if hi - lo > 0:
        proj[:, c] = (proj[:, c] - lo) / (hi - lo) * 255
    else:
        proj[:, c] = 128
proj = proj.astype(np.uint8).reshape(spatial_h, spatial_w, 3)

# Load original image
orig = Image.open(input_path).convert("RGB")
size = 512

orig_resized = orig.resize((size, size), Image.LANCZOS)
feat_nearest = Image.fromarray(proj).resize((size, size), Image.NEAREST)
feat_bilinear = Image.fromarray(proj).resize((size, size), Image.BILINEAR)
overlay = Image.blend(orig_resized, feat_bilinear, alpha=0.5)

canvas = Image.new("RGB", (size * 3, size))
canvas.paste(orig_resized, (0, 0))
canvas.paste(feat_bilinear, (size, 0))
canvas.paste(overlay, (size * 2, 0))

out_path = sys.argv[1].replace(".pt", "_viz.jpg")
canvas.save(out_path, quality=95)
print(f"Saved: {out_path}")
