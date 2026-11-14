import json
import math
from PIL import Image, ImageFilter
import numpy as np

def generate_molecular_face():
    # Load the user-uploaded reference face
    img_path = 'C:/Users/dell/.gemini/antigravity-ide/brain/25b42c89-6acc-4498-9ca9-a08520c80c5b/.user_uploaded/media_1789764410232.png'
    img = Image.open(img_path).convert('RGBA')
    w, h = img.size
    print(f"Loaded reference face image: {w}x{h}")
    
    arr = np.array(img)
    r = arr[:, :, 0].astype(float)
    g = arr[:, :, 1].astype(float)
    b = arr[:, :, 2].astype(float)
    a = arr[:, :, 3].astype(float) / 255.0
    
    # Calculate luminance with gold weighting
    lum = (r * 0.42 + g * 0.42 + b * 0.16) * a
    
    # Generate Sobel edge image for crisp facial feature definition
    gray_img = Image.fromarray(lum.astype(np.uint8))
    edges = gray_img.filter(ImageFilter.FIND_EDGES)
    edge_arr = np.array(edges).astype(float)
    
    # Face center and landmarks in image coordinates
    # Center of face is approx (240, 195)
    cx, cy = 240.0, 195.0
    
    # Scale factor to world units (Three.js space)
    # Target scale: face width ~ 110 units, height ~ 130 units
    scale_x = 105.0 / (w / 2.0)
    scale_y = 120.0 / (h / 2.0)
    
    molecules = []
    
    # 1. Base grid sampling (step = 2 for high density, ~25,000 points)
    step = 2
    for y in range(2, h - 2, step):
        for x in range(2, w - 2, step):
            val = lum[y, x]
            edge_val = edge_arr[y, x]
            
            # Require minimum luminance
            if val < 22 and edge_val < 30:
                continue
            
            # World coordinates centered
            wx = (x - cx) * scale_x
            wy = -(y - cy) * scale_y
            
            # Compute anatomical 3D depth (z)
            # Distance from nose / face center
            dist_center = math.sqrt(((x - 240) / 120.0)**2 + ((y - 195) / 140.0)**2)
            
            # Natural facial 3D dome curvature
            base_z = math.sqrt(max(0.0, 1.0 - min(1.0, dist_center**2))) * 22.0 - 10.0
            
            # Assign specific facial regions:
            # region 1: Upper lip
            # region 2: Lower lip
            # region 3: Chin / jaw
            # region 4: Eyes / irises
            # region 5: Hair curls
            # region 0: Face skin
            region = 0
            
            # Left Eye: x in [185..235], y in [140..170]
            # Right Eye: x in [255..295], y in [140..170]
            if (185 <= x <= 235 and 140 <= y <= 170) or (255 <= x <= 295 and 140 <= y <= 170):
                region = 4
                base_z -= 3.5 # Recessed eye socket
                
            # Nose bridge & tip: x in [225..258], y in [145..205]
            elif 225 <= x <= 258 and 145 <= y <= 205:
                # Protruding nose tip
                nose_factor = 1.0 - math.sqrt(((x - 240) / 18.0)**2 + ((y - 188) / 22.0)**2)
                if nose_factor > 0:
                    base_z += nose_factor * 14.0
                    
            # Upper lip: x in [215..268], y in [206..226]
            elif 215 <= x <= 268 and 206 <= y <= 226:
                region = 1
                base_z += 5.0 # Plump upper lip
                
            # Lower lip: x in [215..268], y in [227..245]
            elif 215 <= x <= 268 and 227 <= y <= 245:
                region = 2
                base_z += 6.5 # Full lower lip
                
            # Chin: x in [215..268], y in [246..280]
            elif 215 <= x <= 268 and 246 <= y <= 280:
                region = 3
                base_z += 2.0 # Sculpted chin
                
            # Outer curls / Hair: distance > 0.65 or y < 110 or x < 150 or x > 330
            elif dist_center > 0.65 or y < 110 or x < 150 or x > 330:
                region = 5
                # Volumetric 3D curls with curly wave dispersion
                hair_wave = math.sin(x * 0.15) * math.cos(y * 0.15) * 12.0
                base_z = base_z * 0.6 + hair_wave
                
            # Point color: rich golden amber with cyan core highlights on eyes/lips
            red_val = int(min(255, r[y, x] * 1.1 + 25))
            green_val = int(min(245, g[y, x] * 1.05 + 15))
            blue_val = int(max(15, min(230, b[y, x] * 0.75)))
            
            # Eyes get sparkling cyan-gold cybernetic tint
            if region == 4 and edge_val > 40:
                blue_val = min(255, blue_val + 70)
                green_val = min(255, green_val + 30)
                
            # Molecule size: proportional to brightness and edge significance
            pt_size = round(1.2 + (val / 255.0) * 2.8 + (edge_val / 255.0) * 1.5, 2)
            
            # Subtle random phase for floating motion
            phase = round((x * 17 + y * 31) % 628 / 100.0, 2)
            
            molecules.append([
                round(wx, 2),
                round(wy, 2),
                round(base_z, 2),
                red_val,
                green_val,
                blue_val,
                pt_size,
                region,
                phase
            ])
            
    print(f"Sampled {len(molecules)} core facial molecules!")
    
    # 2. Add extra edge-sharpening molecules on key contours (eyes, lips, nose, eyelashes)
    edge_pts = 0
    for y in range(3, h - 3, 1):
        for x in range(3, w - 3, 1):
            edge_val = edge_arr[y, x]
            if edge_val > 75:
                # Is it near eyes or mouth?
                is_eye = (185 <= x <= 235 and 140 <= y <= 170) or (255 <= x <= 295 and 140 <= y <= 170)
                is_mouth = (215 <= x <= 268 and 206 <= y <= 250)
                is_nose = (228 <= x <= 255 and 150 <= y <= 202)
                
                if is_eye or is_mouth or is_nose:
                    wx = (x - cx) * scale_x
                    wy = -(y - cy) * scale_y
                    dist_center = math.sqrt(((x - 240) / 120.0)**2 + ((y - 195) / 140.0)**2)
                    base_z = math.sqrt(max(0.0, 1.0 - min(1.0, dist_center**2))) * 22.0 - 10.0
                    
                    region = 0
                    if is_eye:
                        region = 4
                        base_z -= 3.5
                    elif is_mouth:
                        region = 1 if y <= 226 else 2
                        base_z += 6.0
                    elif is_nose:
                        base_z += 12.0
                        
                    molecules.append([
                        round(wx, 2),
                        round(wy, 2),
                        round(base_z, 2),
                        255, 235, 120, # Bright radiant gold
                        3.2, # Slightly larger sharp node
                        region,
                        round((x * 13 + y * 29) % 628 / 100.0, 2)
                    ])
                    edge_pts += 1
                    
    print(f"Added {edge_pts} high-clarity feature contour molecules!")
    
    # 3. Add floating ambient celestial molecules (region 6) around the face
    np.random.seed(42)
    ambient_pts = 1200
    for _ in range(ambient_pts):
        angle = np.random.uniform(0, math.pi * 2)
        radius = np.random.uniform(45, 120)
        wx = math.cos(angle) * radius * 1.15
        wy = math.sin(angle) * radius * 1.25
        wz = np.random.uniform(-35, 35)
        
        molecules.append([
            float(round(wx, 2)),
            float(round(wy, 2)),
            float(round(wz, 2)),
            int(np.random.choice([255, 240, 210])),
            int(np.random.choice([195, 215, 230])),
            int(np.random.choice([60, 120, 180])),
            float(round(np.random.uniform(1.0, 2.6), 2)),
            6, # ambient floating dust
            float(round(np.random.uniform(0, 6.28), 2))
        ])
        
    print(f"Total floating molecules generated: {len(molecules)}")
    
    # Save to static directory
    out_path = 'zohra/api/static/zohra_floating_molecules.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(molecules, f)
    print(f"Saved complete floating molecular face dataset to {out_path}!")
    
if __name__ == '__main__':
    generate_molecular_face()
