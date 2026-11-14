import json
import math
from PIL import Image
import numpy as np

def extract_master_molecules():
    img_path = 'zohra/api/static/zohra_face_master.png'
    img = Image.open(img_path).convert('RGBA')
    w, h = img.size
    arr = np.array(img)
    
    r_chan = arr[:, :, 0].astype(float)
    g_chan = arr[:, :, 1].astype(float)
    b_chan = arr[:, :, 2].astype(float)
    a_chan = arr[:, :, 3].astype(float) / 255.0
    
    # Gold brightness
    gold_lum = (r_chan * 0.45 + g_chan * 0.45 + b_chan * 0.1) * a_chan
    
    # Peak detection for constellation stars
    nodes = []
    step = 4
    for y in range(8, h - 8, step):
        for x in range(8, w - 8, step):
            val = gold_lum[y, x]
            if val < 85:
                continue
            
            # Local maximum check in a 5x5 window
            win = gold_lum[y-2:y+3, x-2:x+3]
            if val >= np.max(win):
                # Normalized coords: -1 to 1 (aspect ratio preserved)
                nx = (x - w / 2.0) / (w / 2.0) * 82.0
                ny = -(y - h / 2.0) / (h / 2.0) * 68.0
                
                # Assign region: 1: mouth/lip, 2: chin, 0: other
                # In image: mouth is roughly x: 215-300, y: 215-255
                region = 0
                if abs(x - 258) < 46 and y >= 212 and y <= 252:
                    region = 1 # mouth
                elif abs(x - 258) < 40 and y > 252 and y <= 285:
                    region = 2 # chin/jaw
                
                r = min(255, int(r_chan[y, x] * 1.1 + 20))
                g = min(245, int(g_chan[y, x] * 1.0 + 15))
                b = max(10, int(b_chan[y, x] * 0.6))
                
                size = round(1.2 + (val / 255.0) * 2.8, 2)
                
                nodes.append([
                    round(nx, 2),
                    round(ny, 2),
                    r, g, b,
                    size,
                    region
                ])
                
    print(f"Extracted {len(nodes)} golden constellation nodes from master face!")
    with open('zohra/api/static/zohra_master_nodes.json', 'w', encoding='utf-8') as f:
        json.dump(nodes, f)
    print("Saved to zohra/api/static/zohra_master_nodes.json")

if __name__ == '__main__':
    extract_master_molecules()
