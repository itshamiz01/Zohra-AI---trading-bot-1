"""
Generate the Zohra molecular face CORRECTLY:
- Use STOCHASTIC (random) sampling - NO grid! 
- Brightness-weighted random sampling
- Face must look like a real beautiful girl
- Variable-size glowing particles
- Thin constellation lines between nearby bright nodes
"""
import json
import math
import random
import numpy as np
from PIL import Image, ImageFilter

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        return super().default(obj)

random.seed(42)
np.random.seed(42)

# Load the best reference - ref_2 is front-facing, clear girl face
img_path = 'scratch/user_ref_2.jpg'
img = Image.open(img_path).convert('RGB')
W, H = img.size
print(f"Reference image: {W}x{H}")

arr = np.array(img, dtype=np.float32)
R = arr[:,:,0]
G = arr[:,:,1]
B = arr[:,:,2]

# Gold luminance
lum = R * 0.45 + G * 0.42 + B * 0.13

# Slight blur for sampling stability
lum_smooth = np.array(Image.fromarray(lum.astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.7)), dtype=np.float32)

# Edges for constellation lines / contour stars
edges = np.array(Image.fromarray(lum.astype(np.uint8)).filter(ImageFilter.FIND_EDGES), dtype=np.float32)

# --- Normalize lum to probability map (0..1) ---
lum_prob = lum_smooth / 255.0

# Face center & scale for Three.js world coords
# Reference face in image: center roughly (490, 360), extends ~400x500 pixels
CX = 490.0
CY = 360.0
# Scale: world space -65..+65 X, -75..+75 Y
SCALE = 130.0 / W  # maps 0..1024 pixel width -> ~130 units

print(f"Face center: ({CX}, {CY}), world scale: {SCALE:.4f}")

# ===========================
# STOCHASTIC IMPORTANCE SAMPLING
# ===========================
# Build normalized probability array for sampling
prob_flat = lum_prob.flatten()
prob_flat = np.maximum(prob_flat, 0.0)
prob_sum = prob_flat.sum()
prob_flat = prob_flat / prob_sum

# Number of molecules to sample
N_MOLECULES = 35000

# Sample pixel indices according to brightness probability
sampled_flat = np.random.choice(len(prob_flat), size=N_MOLECULES, replace=False, p=prob_flat)

# Filter: only keep pixels above minimum lum threshold
MIN_LUM = 25
sampled_flat = sampled_flat[lum_prob.flatten()[sampled_flat] * 255 > MIN_LUM]
print(f"After luminance filter: {len(sampled_flat)} molecules")

# Add extra jitter so particles don't look like a grid
jitter = np.random.uniform(-0.8, 0.8, size=(len(sampled_flat), 2))

# Face region landmarks (in 1024x763 image)
# Left eye center: (415, 310), Right eye center: (560, 310)
# Nose tip: (490, 420)  
# Upper lip center: (490, 495)
# Lower lip center: (490, 520)
# Chin: (490, 580)

def get_region(px, py):
    """
    Returns (region_code, speech_weight)
    speech_weight: +1 = lower lip/jaw (moves down when speaking)
                   -1 = upper lip (moves up slightly when speaking)
                    0 = stationary
    """
    # Upper lip band
    if 440 <= px <= 540 and 480 <= py <= 505:
        return 1, -1.0 * max(0, 1.0 - abs(px - 490) / 52.0)
    # Lower lip + jaw band
    if 435 <= px <= 545 and 506 <= py <= 545:
        return 2, +1.0 * max(0, 1.0 - abs(px - 490) / 55.0)
    # Chin
    if 445 <= px <= 535 and 546 <= py <= 590:
        return 3, +0.55 * max(0, 1.0 - abs(px - 490) / 45.0)
    return 0, 0.0

def face_z_depth(px, py):
    """Smooth 3D head/face depth from 2D pixel coords"""
    # Normalized distance from face center
    dx = (px - CX) / 400.0
    dy = (py - CY) / 480.0
    
    # Base head dome (ellipsoid)
    r2 = (dx * 1.1)**2 + (dy * 0.95)**2
    dome = math.sqrt(max(0.0, 1.0 - min(1.0, r2))) * 26.0 - 10.0
    
    # Nose protrusion (peak at 490, 420)
    d_nose = ((px - 490)/28.0)**2 + ((py - 420)/50.0)**2
    nose_z = math.exp(-d_nose * 0.8) * 15.0
    
    # Left eye socket recession
    d_el = ((px - 415)/34.0)**2 + ((py - 310)/24.0)**2
    # Right eye socket recession  
    d_er = ((px - 560)/34.0)**2 + ((py - 310)/24.0)**2
    eye_z = -(math.exp(-d_el) + math.exp(-d_er)) * 7.0
    
    # Eyeball slight bulge inside sockets
    d_bl = ((px - 415)/17.0)**2 + ((py - 310)/14.0)**2
    d_br = ((px - 560)/17.0)**2 + ((py - 310)/14.0)**2
    ball_z = (math.exp(-d_bl) + math.exp(-d_br)) * 4.2
    
    # Cheekbones
    d_cl = ((px - 380)/50.0)**2 + ((py - 390)/42.0)**2
    d_cr = ((px - 600)/50.0)**2 + ((py - 390)/42.0)**2
    cheek_z = (math.exp(-d_cl) + math.exp(-d_cr)) * 5.5
    
    # Lips volume
    d_lip = ((px - 490)/46.0)**2 + ((py - 508)/28.0)**2
    lip_z = math.exp(-d_lip * 0.9) * 7.5
    
    # Chin
    d_chin = ((px - 490)/40.0)**2 + ((py - 575)/32.0)**2
    chin_z = math.exp(-d_chin) * 4.5
    
    # Volumetric 3D hair curls (spiraling)
    if r2 > 0.5 or py < 200:
        hair_z = math.sin(px * 0.07 + py * 0.03) * math.cos(py * 0.07 - px * 0.03) * 12.0
        return dome * 0.5 + hair_z
    
    return dome + nose_z + eye_z + ball_z + cheek_z + lip_z + chin_z

# Build molecules
molecules = []
for idx, flat_idx in enumerate(sampled_flat):
    py_base = int(flat_idx // W)
    px_base = int(flat_idx % W)
    
    px = float(np.clip(px_base + jitter[idx, 0] * 1.2, 0, W-1))
    py = float(np.clip(py_base + jitter[idx, 1] * 1.2, 0, H-1))
    
    ipx = int(px)
    ipy = int(py)
    
    lv = lum[ipy, ipx]
    if lv < MIN_LUM:
        continue
    
    # World coords
    wx = (px - CX) * SCALE
    wy = -(py - CY) * SCALE  # Flip Y for Three.js
    wz = face_z_depth(px, py)
    
    # Add small random z jitter for sparkle
    wz += np.random.uniform(-0.6, 0.6)
    
    # Gamma-enhanced contrast: preserve dark regions for eye/shadow definition
    # Keep lum-proportional colors — don't over-boost
    t = (lv / 255.0) ** 0.82  # slight gamma lift
    
    # Gold color mapping:
    # Dark regions -> deep amber (30,18,5)
    # Mid regions  -> golden (200,130,40)
    # Bright faces -> warm white-gold (255,220,120)
    # Peak highlights -> brilliant white (255,255,200)
    gold_r = int(np.clip(30 + t * 225, 0, 255))
    gold_g = int(np.clip(12 + t * 200, 0, 255))
    gold_b = int(np.clip(2  + t * 130, 0, 255))
    
    # Add a tiny bit of the original image color to keep golden tones with texture
    rv = int(np.clip(gold_r * 0.75 + R[ipy, ipx] * 0.25, 0, 255))
    gv = int(np.clip(gold_g * 0.75 + G[ipy, ipx] * 0.25, 0, 255))
    bv = int(np.clip(gold_b * 0.75 + B[ipy, ipx] * 0.15, 0, 255))
    
    # Very bright nodes get a brilliant white-gold flare
    if lv > 175:
        rv = 255
        gv = min(255, int(200 + (lv - 175) * 2.5))
        bv = int(80 + (lv - 175) * 2)
    
    # Particle size from lum + edge intensity
    ev = float(edges[ipy, ipx])
    size = round(1.4 + (lv / 255.0) * 2.6 + (ev / 255.0) * 1.1, 2)
    
    # Speech deformation weight
    _, sw = get_region(ipx, ipy)
    
    # Random phase for organic floating
    phase = round(float(np.random.uniform(0, 6.28)), 2)
    
    molecules.append([
        round(float(wx), 2),
        round(float(wy), 2),
        round(float(wz), 2),
        rv, gv, bv,
        size,
        round(float(sw), 3),
        phase
    ])

print(f"Total molecules: {len(molecules)}")

# Save
out_path = 'zohra/api/static/zohra_organic_molecules.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump({'molecules': molecules}, f, cls=NumpyEncoder)
print(f"Saved to {out_path}!")
