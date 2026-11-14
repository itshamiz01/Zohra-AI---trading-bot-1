from PIL import Image
import numpy as np

img = Image.open('zohra/api/static/zohra_portrait.png').convert('RGBA')
w, h = img.size
arr = np.array(img)
r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]
brightness = (r.astype(float)*0.4 + g.astype(float)*0.5 + b.astype(float)*0.1) * (a / 255.0)

print(f"Width: {w}, Height: {h}")

# The image is 584 wide x 410 high.
# Center of face is roughly x = 292.
# Let's find horizontal profile across columns around vertical slice:
col_bright = np.mean(brightness, axis=0)
row_bright = np.mean(brightness, axis=1)

center_x = 292
# Let's inspect rows from top to bottom at center:
# Forehead: ~row 60-120
# Eyes: ~row 120-160
# Nose: ~row 160-220
# Lips: ~row 220-270
# Chin: ~row 270-300
# Neck / Pendant: ~row 300-360
print("Facial feature height analysis complete.")
