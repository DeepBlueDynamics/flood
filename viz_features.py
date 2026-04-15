"""Visualize V-JEPA 2.1 dense features as PCA-RGB grid (paper method)."""
import sys
import math
import itertools
import numpy as np
import torch
from PIL import Image
from decord import VideoReader, cpu

data = torch.load(sys.argv[1], weights_only=False)
features = data["features"].squeeze(0).float().numpy()
input_path = data.get("input", data.get("video"))
n_sampled = data["frames_sampled"]

# 384px / patch_size=16 = 24x24 spatial tokens
n_tokens = features.shape[0]
spatial_h, spatial_w = 24, 24
n_spatial = spatial_h * spatial_w
n_temporal = n_tokens // n_spatial

if n_temporal * n_spatial != n_tokens:
    n_spatial = n_tokens // n_sampled
    n_temporal = n_sampled
    spatial_h = spatial_w = int(math.isqrt(n_spatial))

print(f"Tokens: {n_tokens} = {n_temporal} temporal x {spatial_h}x{spatial_w} spatial")

features = features.reshape(n_temporal, spatial_h, spatial_w, -1)

# PCA to 3 components (global across all tokens)
flat = features.reshape(-1, features.shape[-1])
mean = flat.mean(axis=0)
centered = flat - mean
cov = centered.T @ centered / len(centered)
eigvals, eigvecs = np.linalg.eigh(cov)
top3 = eigvecs[:, -3:][:, ::-1]
proj = centered @ top3  # (N, 3)

# Normalize each component to [0, 255] using 1st/99th percentile
for c in range(3):
    lo, hi = np.percentile(proj[:, c], 1), np.percentile(proj[:, c], 99)
    if hi - lo > 0:
        proj[:, c] = np.clip((proj[:, c] - lo) / (hi - lo) * 255, 0, 255)
    else:
        proj[:, c] = 128
proj = proj.astype(np.uint8).reshape(n_temporal, spatial_h, spatial_w, 3)

# Paper method: try all 6 RGB permutations, pick the one with best visual contrast
# (highest variance in the luminance channel as a heuristic)
perms = list(itertools.permutations([0, 1, 2]))
best_perm = None
best_score = -1
for perm in perms:
    remapped = proj[:, :, :, list(perm)]
    # Approximate luminance
    lum = 0.299 * remapped[..., 0].astype(float) + 0.587 * remapped[..., 1].astype(float) + 0.114 * remapped[..., 2].astype(float)
    score = lum.std()
    if score > best_score:
        best_score = score
        best_perm = perm

print(f"Best RGB permutation: PC{best_perm[0]+1}→R, PC{best_perm[1]+1}→G, PC{best_perm[2]+1}→B")
proj = proj[:, :, :, list(best_perm)]

# Load video frames
vr = VideoReader(str(input_path), ctx=cpu(0))
total_vid = len(vr)
vid_indices = np.linspace(0, total_vid - 1, n_sampled, dtype=np.int64)
temporal_to_frame = np.linspace(0, n_sampled - 1, n_temporal, dtype=int)

# Grid layout
n_grid = min(16, n_temporal)
t_indices = np.linspace(0, n_temporal - 1, n_grid, dtype=int)
cols = int(math.ceil(math.sqrt(n_grid)))
rows = int(math.ceil(n_grid / cols))
cell = 256

canvas = Image.new("RGB", (cols * cell * 2, rows * cell))

for i, t_idx in enumerate(t_indices):
    r, c = divmod(i, cols)
    frame_idx = vid_indices[temporal_to_frame[t_idx]]
    frame = vr[int(frame_idx)].asnumpy()
    frame_img = Image.fromarray(frame).resize((cell, cell), Image.LANCZOS)
    feat_img = Image.fromarray(proj[t_idx]).resize((cell, cell), Image.BILINEAR)
    canvas.paste(frame_img, (c * cell * 2, r * cell))
    canvas.paste(feat_img, (c * cell * 2 + cell, r * cell))

out_path = sys.argv[1].replace(".pt", "_viz.jpg")
canvas.save(out_path, quality=95)
print(f"Saved: {out_path}")
