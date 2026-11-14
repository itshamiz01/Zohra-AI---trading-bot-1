import json
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = Path(r"C:\Users\dell\AppData\Local\Temp\codex-clipboard-ac4bf631-952c-46e6-a57c-82d457880fad.png")
OUTPUT = ROOT / "zohra" / "api" / "static" / "zohra_reference_molecules.json"

CX = 249.0
CY = 232.0
SCALE = 178.0 / 458.0


def face_depth(px, py):
    dx = (px - CX) / 126.0
    dy = (py - 232.0) / 174.0
    dome = math.sqrt(max(0.0, 1.0 - min(1.0, dx * dx + (dy * 0.92) ** 2))) * 28.0 - 13.0
    nose = math.exp(-((px - 249.0) / 18.0) ** 2 - ((py - 218.0) / 50.0) ** 2) * 17.0
    bridge = math.exp(-((px - 249.0) / 14.0) ** 2 - ((py - 174.0) / 72.0) ** 2) * 7.0
    eyes = -(
        math.exp(-((px - 204.0) / 26.0) ** 2 - ((py - 175.0) / 18.0) ** 2)
        + math.exp(-((px - 296.0) / 26.0) ** 2 - ((py - 175.0) / 18.0) ** 2)
    ) * 8.0
    eyeballs = (
        math.exp(-((px - 204.0) / 11.0) ** 2 - ((py - 176.0) / 9.0) ** 2)
        + math.exp(-((px - 296.0) / 11.0) ** 2 - ((py - 176.0) / 9.0) ** 2)
    ) * 4.4
    cheeks = (
        math.exp(-((px - 198.0) / 40.0) ** 2 - ((py - 226.0) / 38.0) ** 2)
        + math.exp(-((px - 300.0) / 40.0) ** 2 - ((py - 226.0) / 38.0) ** 2)
    ) * 5.2
    lips = math.exp(-((px - 250.0) / 42.0) ** 2 - ((py - 262.0) / 22.0) ** 2) * 7.4
    chin = math.exp(-((px - 250.0) / 55.0) ** 2 - ((py - 309.0) / 36.0) ** 2) * 4.8
    return dome + nose + bridge + eyes + eyeballs + cheeks + lips + chin


def speech_weight(px, py):
    # The current 499x458 portrait's lip seam is at y=216, not the old y=264.
    u = (px - 250.0) / 39.0
    if abs(u) >= 1 or py < 194 or py >= 262:
        return 0.0
    across = (1 - u * u) ** 1.7
    below = py - (216 - 4 * u * u)
    def smooth(a, b, value):
        t = max(0.0, min(1.0, (value - a) / (b - a)))
        return t * t * (3 - 2 * t)
    return (-0.22 * across * smooth(-22, -2, below) if below <= 0
            else across * (1 - smooth(8, 46, below)))


def skin_mask(px, py):
    face = ((px - CX) / 128.0) ** 2 + ((py - 232.0) / 174.0) ** 2 < 1.0 and 93 <= py <= 327
    neck = abs(px - CX) < 62 and 285 <= py <= 382
    bust = ((px - CX) / 214.0) ** 2 + ((py - 383.0) / 94.0) ** 2 < 1.0 and py >= 308
    return face or neck or bust


def hair_mask(px, py):
    halo = ((px - CX) / 225.0) ** 2 + ((py - 239.0) / 222.0) ** 2 < 1.15
    away_from_face = abs(px - CX) > 72 or py < 146 or py > 292
    return halo and away_from_face and 32 <= py <= 410


def background_network_mask(px, py):
    halo = ((px - CX) / 241.0) ** 2 + ((py - 225.0) / 230.0) ** 2 < 1.32
    core = ((px - CX) / 135.0) ** 2 + ((py - 235.0) / 178.0) ** 2 < 1.0
    return halo and not core


def build():
    random.seed(20092026)
    np.random.seed(20092026)

    img = Image.open(REFERENCE).convert("RGB")
    arr = np.asarray(img, dtype=np.float32)
    h, w = arr.shape[:2]
    gray = (arr[:, :, 0] * 0.50 + arr[:, :, 1] * 0.42 + arr[:, :, 2] * 0.08).astype(np.uint8)
    edges = np.asarray(Image.fromarray(gray).filter(ImageFilter.FIND_EDGES), dtype=np.float32)

    molecules = []
    halo_count = 0

    def add(px, py, layer, size_boost=0.0, alpha_boost=0.0):
        r, g, b = arr[py, px]
        lum = float(gray[py, px])
        edge = float(edges[py, px])
        wx = (px - CX) * SCALE * 1.03
        wy = -(py - CY) * SCALE + 3.5

        if layer == "hair":
            wz = face_depth(px, py) - 11.0 + random.uniform(-4.0, 4.0)
            motion = 0.96
            base_alpha = 0.46
            size_base = 0.72
        elif layer == "network":
            wz = random.uniform(-30.0, 18.0)
            motion = 1.18
            base_alpha = 0.32
            size_base = 0.56
        else:
            wz = face_depth(px, py) + random.uniform(-0.9, 0.9)
            motion = 0.22
            base_alpha = 0.73
            size_base = 1.06

        if lum < 42 and edge < 55:
            red = int(np.clip(r * 0.94 + 18, 18, 190))
            green = int(np.clip(g * 0.86 + 12, 12, 155))
            blue = int(np.clip(b * 0.68 + 4, 4, 88))
        else:
            red = int(np.clip(r * 1.12 + 22 + edge * 0.10, 18, 255))
            green = int(np.clip(g * 1.04 + 16 + edge * 0.08, 12, 246))
            blue = int(np.clip(b * 0.78 + 7 + edge * 0.035, 5, 152))

        if edge > 92 or lum > 172:
            red = int(min(255, red + 34))
            green = int(min(248, green + 27))
            blue = int(min(164, blue + 14))

        size = size_base + (lum / 255.0) * 1.45 + (edge / 255.0) * 0.62 + size_boost
        alpha = min(0.985, base_alpha + (lum / 255.0) * 0.18 + (edge / 255.0) * 0.13 + alpha_boost)
        if layer == "network":
            alpha = min(0.72, alpha)

        molecules.append([
            round(wx, 2),
            round(wy, 2),
            round(wz, 2),
            red,
            green,
            blue,
            round(size, 2),
            round(speech_weight(px, py), 3) if layer == "skin" else 0.0,
            round(random.random() * math.tau, 3),
            round(motion, 2),
            round(alpha, 3),
        ])

    for py in range(12, h - 6):
        for px in range(4, w - 4):
            lum = float(gray[py, px])
            edge = float(edges[py, px])
            in_skin = skin_mask(px, py)
            in_hair = hair_mask(px, py)
            in_network = background_network_mask(px, py)

            if in_skin:
                if lum < 17 and edge < 17:
                    continue
                probability = 0.58 + (lum / 255.0) * 0.34 + (edge / 255.0) * 0.20
                if 132 <= py <= 302 and abs(px - CX) < 129:
                    probability += 0.14
                if random.random() < min(0.99, probability):
                    add(px, py, "skin")
                continue

            if in_hair:
                if lum < 19 and edge < 22:
                    continue
                probability = 0.22 + (lum / 255.0) * 0.30 + (edge / 255.0) * 0.46
                if random.random() < min(0.92, probability):
                    add(px, py, "hair")
                continue

            if in_network and (lum > 48 or edge > 72):
                probability = 0.06 + (lum / 255.0) * 0.18 + (edge / 255.0) * 0.32
                if random.random() < min(0.42, probability):
                    add(px, py, "network", size_boost=-0.12, alpha_boost=-0.08)

    feature_boxes = [
        (174, 154, 228, 197, 0.42, 0.11),
        (270, 154, 324, 197, 0.42, 0.11),
        (163, 131, 235, 166, 0.38, 0.10),
        (263, 131, 336, 166, 0.38, 0.10),
        (225, 173, 274, 245, 0.34, 0.08),
        (206, 240, 296, 283, 0.55, 0.12),
        (182, 290, 318, 330, 0.28, 0.07),
    ]
    for x0, y0, x1, y1, size_boost, alpha_boost in feature_boxes:
        for py in range(y0, y1):
            for px in range(x0, x1):
                lum = float(gray[py, px])
                edge = float(edges[py, px])
                if edge > 52 or lum > 92 or lum < 46:
                    if random.random() < 0.26:
                        add(px, py, "skin", size_boost=size_boost, alpha_boost=alpha_boost)

    # A soft free-particle halo, separate from the portrait, keeps the command-center feel.
    halo_count = 2400
    for _ in range(halo_count):
        a = random.random() * math.tau
        radius = random.uniform(86, 142)
        x = math.cos(a) * radius * random.uniform(0.72, 1.22)
        y = random.uniform(-82, 96)
        z = random.uniform(-40, 24)
        warm = random.uniform(0.0, 1.0)
        molecules.append([
            round(x, 2),
            round(y, 2),
            round(z, 2),
            int(135 + warm * 112),
            int(82 + warm * 132),
            int(18 + warm * 78),
            round(random.uniform(0.55, 1.75), 2),
            0.0,
            round(random.random() * math.tau, 3),
            round(random.uniform(0.82, 1.28), 2),
            round(random.uniform(0.22, 0.48), 3),
        ])

    bonds = []
    core_count = len(molecules) - halo_count
    grid = {}
    cell = 4.8
    for idx, m in enumerate(molecules[:core_count]):
        key = (int(m[0] // cell), int(m[1] // cell))
        grid.setdefault(key, []).append(idx)

    for i in range(0, core_count, 14):
        x, y, z = molecules[i][0], molecules[i][1], molecules[i][2]
        key = (int(x // cell), int(y // cell))
        found = 0
        for gx in range(key[0] - 1, key[0] + 2):
            for gy in range(key[1] - 1, key[1] + 2):
                for j in grid.get((gx, gy), []):
                    if j <= i or j % 4:
                        continue
                    x2, y2, z2 = molecules[j][0], molecules[j][1], molecules[j][2]
                    d2 = (x - x2) ** 2 + (y - y2) ** 2 + ((z - z2) * 0.42) ** 2
                    if 7.5 < d2 < 29.0 and random.random() < 0.30:
                        bonds.extend([i, j])
                        found += 1
                        if found >= 2:
                            break
                if found >= 2:
                    break
            if found >= 2:
                break
        if len(bonds) >= 12000:
            break

    OUTPUT.write_text(
        json.dumps({"molecules": molecules, "bonds": bonds}, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT} with {len(molecules)} molecules and {len(bonds) // 2} bonds")


if __name__ == "__main__":
    build()
