import json
import math
import os
from PIL import Image
import numpy as np

def generate_zohra_molecules():
    img_path = 'zohra/api/static/zohra_portrait.png'
    if not os.path.exists(img_path):
        print("Image not found:", img_path)
        return

    img = Image.open(img_path).convert('RGBA')
    w, h = img.size
    arr = np.array(img)
    
    r_chan = arr[:, :, 0].astype(float)
    g_chan = arr[:, :, 1].astype(float)
    b_chan = arr[:, :, 2].astype(float)
    a_chan = arr[:, :, 3].astype(float) / 255.0
    
    # Brightness favoring golden luminescence
    gold_lum = (r_chan * 0.45 + g_chan * 0.45 + b_chan * 0.1) * a_chan
    
    # Grid sampling with brightness-weighted jitter
    cx, cy = w / 2.0, h / 2.0
    
    # Target ~9,000 points
    points = []
    
    # Landmark centers in image coords (w=584, h=410)
    # Nose center: x=292, y=185
    # Mouth center: x=292, y=225
    # Left eye: x=255, y=140
    # Right eye: x=330, y=140
    # Chin: x=292, y=265
    
    step = 2
    for y in range(10, h - 10, step):
        for x in range(10, w - 10, step):
            lum = gold_lum[y, x]
            if lum < 28:
                continue
            
            # Probability check based on brightness
            prob = min(0.95, (lum / 255.0) ** 1.3 * 1.8)
            if np.random.rand() > prob:
                continue
            
            # Image to 3D centered coordinates (-100 to 100 on X, flipped Y)
            nx = (x - cx) / (w / 2.0) * 85.0
            ny = -(y - cy) / (h / 2.0) * 75.0
            
            # Base 3D head curvature (dome)
            dist_center = math.sqrt((nx / 75.0)**2 + (ny / 70.0)**2)
            z_base = math.cos(min(1.4, dist_center * 1.2)) * 26.0
            
            # Assign anatomical regions and feature depth
            region = 0 # 0: general face
            
            # Mouth region (y in image ~ 205-245, x in image ~ 265-320)
            dx_mouth = x - 292
            dy_mouth = y - 225
            dist_mouth = math.sqrt((dx_mouth / 32.0)**2 + (dy_mouth / 16.0)**2)
            
            # Nose region
            dx_nose = x - 292
            dy_nose = y - 185
            dist_nose = math.sqrt((dx_nose / 22.0)**2 + (dy_nose / 25.0)**2)
            
            # Eyes region
            dx_leye = x - 256
            dy_leye = y - 138
            dist_leye = math.sqrt((dx_leye / 22.0)**2 + (dy_leye / 14.0)**2)
            
            dx_reye = x - 328
            dy_reye = y - 138
            dist_reye = math.sqrt((dx_reye / 22.0)**2 + (dy_reye / 14.0)**2)
            
            # Chin/Jaw region
            dx_chin = x - 292
            dy_chin = y - 268
            dist_chin = math.sqrt((dx_chin / 30.0)**2 + (dy_chin / 18.0)**2)
            
            z = z_base
            
            if dist_nose < 1.0:
                region = 6 # nose
                z += (1.0 - dist_nose) * 14.0
            elif dist_mouth < 1.0:
                if y < 223:
                    region = 1 # upper lip
                    z += (1.0 - dist_mouth) * 8.0
                else:
                    region = 2 # lower lip
                    z += (1.0 - dist_mouth) * 9.0
            elif dist_chin < 1.0:
                region = 3 # jaw / chin
                z += (1.0 - dist_chin) * 4.0
            elif dist_leye < 1.0:
                region = 4 # left eye / eyelid
                z -= (1.0 - dist_leye) * 4.0
            elif dist_reye < 1.0:
                region = 5 # right eye / eyelid
                z -= (1.0 - dist_reye) * 4.0
            elif y > 290 and abs(x - 292) < 40:
                region = 8 # pendant / neck
                z -= 8.0
            elif dist_center > 0.65:
                region = 7 # curly hair volume
                z += (np.random.rand() - 0.5) * 22.0 - 6.0
            else:
                region = 0 # cheeks / forehead
                # subtle cheekbone rise
                if abs(nx) > 20 and ny > -10 and ny < 20:
                    z += 4.5
            
            # Colors
            r = int(arr[y, x, 0])
            g = int(arr[y, x, 1])
            b = int(arr[y, x, 2])
            
            # Enhance golden radiance
            r = min(255, int(r * 1.05 + 15))
            g = min(240, int(g * 0.95 + 10))
            b = max(10, int(b * 0.6))
            
            size = round(1.2 + (lum / 255.0) * 2.2, 2)
            
            points.append([
                round(nx, 2),
                round(ny, 2),
                round(z, 2),
                r, g, b,
                size,
                region
            ])
            
    print(f"Total molecular nodes generated: {len(points)}")
    
    # Save to static directory
    out_path = 'zohra/api/static/zohra_face_molecules.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(points, f)
    print(f"Saved to {out_path}, file size: {os.path.getsize(out_path) / 1024:.1f} KB")

if __name__ == '__main__':
    generate_zohra_molecules()
