from PIL import Image
import numpy as np

src = 'C:/Users/dell/.gemini/antigravity-ide/brain/25b42c89-6acc-4498-9ca9-a08520c80c5b/.user_uploaded/media_1789764410232.png'
img = Image.open(src).convert('RGB')
w, h = img.size
arr = np.array(img, dtype=float)

# Calculate distance from center for edge feathering
cx, cy = w / 2.0, h / 2.0
y_coords, x_coords = np.indices((h, w))
dx = (x_coords - cx) / (w * 0.48)
dy = (y_coords - cy) / (h * 0.48)
dist = np.sqrt(dx**2 + dy**2)

# Edge vignette: fade to transparent near outer boundaries
vignette = 1.0 - np.clip((dist - 0.72) / 0.26, 0.0, 1.0)
vignette = vignette ** 1.5

# Luminance check: pure black pixels near edges should also be transparent
lum = (arr[:, :, 0] * 0.3 + arr[:, :, 1] * 0.6 + arr[:, :, 2] * 0.1)
black_mask = np.clip(lum / 12.0, 0.0, 1.0)

alpha = (vignette * 255.0).astype(np.uint8)

# Create RGBA image
rgba = np.dstack((arr.astype(np.uint8), alpha))
out_img = Image.fromarray(rgba, mode='RGBA')

out_path = 'zohra/api/static/zohra_face_master.png'
out_img.save(out_path, format='PNG')
print(f"Feathered master face saved to {out_path}: {w}x{h}")
