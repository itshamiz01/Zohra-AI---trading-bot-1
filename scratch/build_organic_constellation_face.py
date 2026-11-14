import json
import math
from PIL import Image, ImageFilter
import numpy as np

def generate_masterpiece_face():
    # Load user_ref_2.jpg (1024x763) - front-facing golden constellation face
    ref_path = 'scratch/user_ref_2.jpg'
    img = Image.open(ref_path).convert('RGB')
    w, h = img.size
    print(f"Loaded master reference: {w}x{h}")
    
    arr = np.array(img, dtype=float)
    r = arr[:, :, 0]
    g = arr[:, :, 1]
    b = arr[:, :, 2]
    
    # Gold luminance
    lum = r * 0.45 + g * 0.45 + b * 0.1
    
    # Feature edge detection for sharp contours (eyes, lips, curls)
    gray = Image.fromarray(lum.astype(np.uint8))
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_arr = np.array(edges, dtype=float)
    
    # Face landmarks in user_ref_2.jpg (1024x763):
    # Head center: cx = 485, cy = 370
    cx, cy = 485.0, 370.0
    
    # World scale: map face to ~ 130 Three.js units wide, ~ 150 units high
    scale = 135.0 / (w * 0.5)
    
    molecules = []
    np.random.seed(1337)
    
    # 1. High-Density Organic Point Cloud (Rejection + Jitter Sampling)
    # We want ~32,000 - 38,000 molecules with NO Cartesian grid lines!
    step = 2.5 # Fine sampling step
    y_range = np.arange(40, h - 30, step)
    x_range = np.arange(120, w - 120, step)
    
    for y_base in y_range:
        for x_base in x_range:
            # Add continuous random jitter (-1.2 to +1.2 pixels) to destroy any scan-line grid
            jitter_x = np.random.uniform(-1.1, 1.1)
            jitter_y = np.random.uniform(-1.1, 1.1)
            px = int(np.clip(x_base + jitter_x, 0, w - 1))
            py = int(np.clip(y_base + jitter_y, 0, h - 1))
            
            val = lum[py, px]
            e_val = edge_arr[py, px]
            
            # Acceptance probability based on brightness & edge richness
            # Higher probability on face, eyes, lips, and curly hair
            prob = (val / 255.0) * 0.85 + (e_val / 255.0) * 0.65
            
            # Check distance from head center
            dx_norm = (px - cx) / 360.0
            dy_norm = (py - cy) / 380.0
            dist_sq = dx_norm**2 + dy_norm**2
            
            if dist_sq > 1.2:
                # Outside head halo - only keep ambient stars
                if np.random.random() > 0.03 or val < 40:
                    continue
            else:
                if np.random.random() > prob and val < 28:
                    continue
            
            # Three.js coordinates (centered)
            wx = (px - cx) * scale
            wy = -(py - cy) * scale
            
            # 2. Smooth Continuous 3D Depth Function (No sharp steps or rectangular cutouts!)
            # Base head dome (smooth ellipsoid)
            rad_head = math.sqrt(max(0.0, 1.0 - min(1.0, (dx_norm * 1.1)**2 + (dy_norm * 0.95)**2)))
            z_depth = rad_head * 24.0 - 12.0
            
            # Smooth anatomical facial features:
            # Nose bridge & tip: peak around (485, 385), width 28, height 55
            d_nose = ((px - 485.0) / 26.0)**2 + ((py - 385.0) / 52.0)**2
            z_nose = math.exp(-d_nose) * 16.5
            
            # Eye socket recession (smooth negative Gaussian at left eye 418,312 and right eye 552,312)
            d_eye_l = ((px - 418.0) / 32.0)**2 + ((py - 312.0) / 22.0)**2
            d_eye_r = ((px - 552.0) / 32.0)**2 + ((py - 312.0) / 22.0)**2
            z_eyes = - (math.exp(-d_eye_l) + math.exp(-d_eye_r)) * 6.5
            
            # Eyeball curvature (slight positive bulge inside socket)
            d_ball_l = ((px - 418.0) / 16.0)**2 + ((py - 312.0) / 14.0)**2
            d_ball_r = ((px - 552.0) / 16.0)**2 + ((py - 312.0) / 14.0)**2
            z_ball = (math.exp(-d_ball_l) + math.exp(-d_ball_r)) * 3.8
            
            # Cheekbone contour
            d_chk_l = ((px - 385.0) / 45.0)**2 + ((py - 385.0) / 35.0)**2
            d_chk_r = ((px - 585.0) / 45.0)**2 + ((py - 385.0) / 35.0)**2
            z_cheek = (math.exp(-d_chk_l) + math.exp(-d_chk_r)) * 5.0
            
            # Lip volume: smooth positive Gaussian at (485, 498)
            d_lips = ((px - 485.0) / 42.0)**2 + ((py - 498.0) / 22.0)**2
            z_lips = math.exp(-d_lips) * 7.0
            
            # Chin volume: smooth positive Gaussian at (485, 575)
            d_chin = ((px - 485.0) / 36.0)**2 + ((py - 575.0) / 28.0)**2
            z_chin = math.exp(-d_chin) * 4.5
            
            # Hair curls volumetric wave (cascading 3D spirals around perimeter)
            z_hair = 0.0
            if dist_sq > 0.45 or py < 240:
                z_hair = math.sin(px * 0.08) * math.cos(py * 0.08) * 14.0
                
            wz = z_depth + z_nose + z_eyes + z_ball + z_cheek + z_lips + z_chin + z_hair
            
            # 3. True Color from Reference
            red = int(np.clip(r[py, px] * 1.08 + 10, 0, 255))
            green = int(np.clip(g[py, px] * 1.04 + 5, 0, 255))
            blue = int(np.clip(b[py, px] * 0.85, 0, 255))
            
            # Ensure bright golden stars have glowing core
            if val > 160:
                red = 255
                green = min(255, green + 35)
                blue = max(100, blue)
                
            # Point size proportional to star brightness
            size = round(1.3 + (val / 255.0) * 2.8 + (e_val / 255.0) * 1.2, 2)
            
            # Continuous speech deformation weight (Gaussian around mouth / chin)
            # Center at (485, 510), width 55, height 65
            d_mouth_speech = ((px - 485.0) / 58.0)**2 + ((py - 515.0) / 55.0)**2
            speech_weight = round(float(math.exp(-d_mouth_speech)), 3)
            
            # Distinguish upper lip vs lower lip / jaw
            is_lower = 1 if py > 500 else -1
            if speech_weight < 0.05:
                speech_weight = 0.0
                
            # Random phase for organic floating
            phase = round(float(np.random.uniform(0, 6.28)), 2)
            
            molecules.append([
                round(float(wx), 2),
                round(float(wy), 2),
                round(float(wz), 2),
                red,
                green,
                blue,
                size,
                speech_weight * is_lower, # Negative for upper lip, positive for lower lip/jaw
                phase
            ])
            
    print(f"Generated {len(molecules)} organic golden molecules from user_ref_2.jpg!")
    
    # 4. Extract Bright Constellation Star Flare Nodes
    # Find local maxima in 11x11 windows to extract the exact constellation nodes shown in the art!
    star_nodes = []
    step_node = 6
    for y in range(50, h - 50, step_node):
        for x in range(120, w - 120, step_node):
            v = lum[y, x]
            if v > 115:
                win = lum[y-3:y+4, x-3:x+4]
                if v >= np.max(win):
                    wx = (x - cx) * scale
                    wy = -(y - cy) * scale
                    # Find depth
                    dx_n = (x - cx) / 360.0
                    dy_n = (y - cy) / 380.0
                    rad = math.sqrt(max(0.0, 1.0 - min(1.0, (dx_n*1.1)**2 + (dy_n*0.95)**2)))
                    wz = rad * 24.0 - 12.0
                    if ((x - 485.0)/26.0)**2 + ((y - 385.0)/52.0)**2 < 1.0:
                        wz += 16.0
                    
                    star_nodes.append([round(float(wx), 2), round(float(wy), 2), round(float(wz), 2)])
                    
    print(f"Extracted {len(star_nodes)} major constellation flare nodes!")
    
    # Save dataset
    output = {
        'molecules': molecules,
        'star_nodes': star_nodes
    }
    out_file = 'zohra/api/static/zohra_organic_molecules.json'
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(output, f)
    print(f"Saved complete organic dataset to {out_file}!")

if __name__ == '__main__':
    generate_masterpiece_face()
