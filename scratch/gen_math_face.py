"""
ZOHRA FACE v5 - REAL BEAUTIFUL GIRL FACE
==========================================
Completely fixed proportions. NO ghost, NO skull, NO horns.
Beautiful woman constellation face like the reference image.

Key fixes:
- Eyes BRIGHT (no dark skull sockets)
- Hair contained (no horn side wings)
- Proper skin-glow across entire face
- Natural feminine features
- Correct human proportions
"""
import json, math, random, numpy as np

random.seed(999)
np.random.seed(999)

class E(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (np.integer,)): return int(o)
        if isinstance(o, (np.floating,)): return float(o)
        return super().default(o)

molecules = []

def gold(b):
    b = float(np.clip(b, 0, 1))
    return (int(25 + b*230), int(8 + b*190), int(b*75))

def pt(x, y, z, b=0.65, sz=None, sw=0.0):
    r,g,bl = gold(b)
    if sz is None: sz = round(1.2 + b*2.0, 2)
    molecules.append([round(float(x),2), round(float(y),2), round(float(z),2),
                      r, g, bl, sz, round(float(sw),3), round(random.uniform(0,6.28),2)])

def blob(cx, cy, cz, rx, ry, rz, n, b=(0.3,0.8), sw=0.0, s=(1.2,2.8)):
    for _ in range(n):
        for _ in range(20):
            dx,dy,dz = random.gauss(0,rx*.44), random.gauss(0,ry*.44), random.gauss(0,rz*.44)
            if (dx/rx)**2+(dy/ry)**2+(dz/rz)**2 <= 1.0: break
        bv = random.uniform(*b)
        r,g,bl = gold(bv)
        swv = sw * max(0, 1-math.sqrt((dx/rx)**2+(dy/ry)**2))
        molecules.append([round(cx+dx,2), round(cy+dy,2), round(cz+dz,2),
                          r,g,bl, round(random.uniform(*s),2), round(swv,3), round(random.uniform(0,6.28),2)])

def arc(pts, n, b=0.72, sz=2.0, sw=0.0, noise=0.25, z=0):
    for i in range(n):
        t = i/max(1,n-1)
        s = t*(len(pts)-1); si=int(s); sf=s-si
        if si>=len(pts)-1: si,sf=len(pts)-2,1.0
        px = pts[si][0]*(1-sf)+pts[si+1][0]*sf
        py = pts[si][1]*(1-sf)+pts[si+1][1]*sf
        pt(px+random.gauss(0,noise), py+random.gauss(0,noise*.7),
           z+random.gauss(0,noise*.4), b+random.uniform(-.07,.07), sz+random.uniform(-.2,.2), sw)

def oval(cx,cy,cz,rx,ry,n,b=0.72,sz=2.0,sw=0.0,noise=0.3):
    for i in range(n):
        t = 2*math.pi*i/n
        pt(cx+rx*math.cos(t)+random.gauss(0,noise),
           cy+ry*math.sin(t)+random.gauss(0,noise*.8),
           cz+random.gauss(0,noise*.4), b+random.uniform(-.08,.08), sz+random.uniform(-.2,.2), sw)

# ═══════════════════════════════════════════════════════════════════
# FACE COORDINATES (all in Three.js world units)
# Face center Y=0, spans Y: -28 (chin) to +30 (forehead top)
# Face width: ±16 units | Eyes at ±6 units (natural spacing)
# ═══════════════════════════════════════════════════════════════════

# ── SKIN BASE (entire face filled with warm golden molecules) ───────
# Main face oval - dense warm glow
blob(0, 2, 2,  rx=16, ry=26, rz=8,  n=6500, b=(0.28,0.72), s=(1.0,2.4))
# Extra skin warmth on cheek/nose area
blob(0, 0, 5,  rx=10, ry=15, rz=4,  n=1800, b=(0.45,0.82), s=(1.5,2.8))

# ── FACE OUTLINE ────────────────────────────────────────────────────
oval(0, 1, 0,  rx=16, ry=27, n=320, b=0.70, sz=1.8, noise=0.35)

# ── HAIR (contained, natural, no horns) ─────────────────────────────
# Top of head - rounded dome of hair
blob(0,  32, -2, rx=16, ry=9,  rz=6, n=1400, b=(0.12,0.42), s=(1.0,2.4))
blob(0,  26, -2, rx=18, ry=4,  rz=5, n=600,  b=(0.14,0.40), s=(1.0,2.2))
# Left hair — flows DOWN naturally beside face, stays close
blob(-14, 15, -4, rx=5,  ry=16, rz=4, n=700,  b=(0.10,0.38), s=(1.0,2.2))
blob(-12,  2, -5, rx=4,  ry=10, rz=3, n=400,  b=(0.10,0.35), s=(1.0,2.0))
# Right hair
blob( 14, 15, -4, rx=5,  ry=16, rz=4, n=700,  b=(0.10,0.38), s=(1.0,2.2))
blob( 12,  2, -5, rx=4,  ry=10, rz=3, n=400,  b=(0.10,0.35), s=(1.0,2.0))
# Hair curl strands (small, close to face, not sticking out)
for i in range(5):
    blob(-13-i, 22-i*5, -5, rx=2.5,ry=3,rz=2, n=70, b=(0.10,0.35), s=(1.0,2.0))
    blob( 13+i, 22-i*5, -5, rx=2.5,ry=3,rz=2, n=70, b=(0.10,0.35), s=(1.0,2.0))

# ── FOREHEAD ─────────────────────────────────────────────────────────
blob(0, 21, 6, rx=13, ry=6, rz=4, n=420, b=(0.55,0.85), s=(1.5,2.8))

# ── EYEBROWS (arched, defined) ───────────────────────────────────────
arc([(-11,14),(-8,15.5),(-5.5,15),(-3.5,14.2)], 85, b=0.92, sz=2.6, noise=0.20, z=9)
arc([( 11,14),( 8,15.5),( 5.5,15),( 3.5,14.2)], 85, b=0.92, sz=2.6, noise=0.20, z=9)
blob(-7.5,15,8.5, rx=3.5,ry=0.7,rz=0.5, n=60, b=(0.78,0.92), s=(1.8,2.4))
blob( 7.5,15,8.5, rx=3.5,ry=0.7,rz=0.5, n=60, b=(0.78,0.92), s=(1.8,2.4))

# ── EYES (BRIGHT and BEAUTIFUL — no dark sockets!) ──────────────────
# LEFT EYE center (-6, 10) — almond shaped
oval(-6, 10, 8, rx=4.2, ry=2.2, n=130, b=0.90, sz=2.3, noise=0.20)
# Bright iris (golden glow — eyes look alive, not skull!)
blob(-6, 10, 9.5, rx=2.0,ry=2.0,rz=0.8, n=300, b=(0.68,0.86), s=(2.0,3.2))
# Pupil: bright WHITE hot center (not dark — makes eyes look alive!)
blob(-6, 10,10.5, rx=0.9,ry=0.9,rz=0.3, n=60,  b=(0.65,0.80), s=(2.2,3.2))
# Eyelid creases
arc([(-10.5,11),(-6,12.8),(-2.2,11)], 55, b=0.72, sz=1.8, noise=0.22, z=9)
arc([(-10,9.2),(-6,8.2),(-2.5,9.2)], 44, b=0.60, sz=1.6, noise=0.22, z=9)

# RIGHT EYE center (6, 10)
oval( 6, 10, 8, rx=4.2, ry=2.2, n=130, b=0.90, sz=2.3, noise=0.20)
blob( 6, 10, 9.5, rx=2.0,ry=2.0,rz=0.8, n=300, b=(0.68,0.86), s=(2.0,3.2))
blob( 6, 10,10.5, rx=0.9,ry=0.9,rz=0.3, n=60,  b=(0.65,0.80), s=(2.2,3.2))
arc([( 2.2,11),( 6,12.8),(10.5,11)], 55, b=0.72, sz=1.8, noise=0.22, z=9)
arc([( 2.5,9.2),( 6,8.2),(10,9.2)], 44, b=0.60, sz=1.6, noise=0.22, z=9)

# Eye corner sparkle (catchlights)
for ex,ey in [(-10.5,10.5),(-2.2,10.5),(10.5,10.5),(2.2,10.5)]:
    blob(ex,ey,10, rx=0.8,ry=0.7,rz=0.4, n=15, b=(0.92,1.00), s=(3.0,5.2))

# ── NOSE ─────────────────────────────────────────────────────────────
# Slim bridge (straight down)
arc([(0,9),(0,4.5),(0,0)], 65, b=0.65, sz=1.8, noise=0.28, z=9.5)
arc([(-1.2,6.5),(-1.5,2),(-2.2,-1.5)], 40, b=0.55, sz=1.5, noise=0.25, z=8.8)
arc([( 1.2,6.5),( 1.5,2),( 2.2,-1.5)], 40, b=0.55, sz=1.5, noise=0.25, z=8.8)
# Nose tip (soft, not sharp)
blob(0,-2,11, rx=2.0,ry=1.8,rz=1.4, n=160, b=(0.70,0.92), s=(1.8,3.0))
# Nostrils (warm glow — not dark holes)
blob(-2.8,-4,8.5, rx=2.2,ry=1.4,rz=1.0, n=90, b=(0.48,0.72), s=(1.5,2.4))
blob( 2.8,-4,8.5, rx=2.2,ry=1.4,rz=1.0, n=90, b=(0.48,0.72), s=(1.5,2.4))
# Philtrum
arc([(0,-5.5),(0,-7),(0,-8.5)], 30, b=0.52, sz=1.4, noise=0.25, z=9.5)

# ── LIPS (full, beautiful, feminine) ─────────────────────────────────
# Upper lip - cupid bow
ulip = [(-6.5,-9.5),(-4,-8.8),(-2,-9.5),(0,-9.0),(2,-9.5),(4,-8.8),(6.5,-9.5)]
arc(ulip, 140, b=0.88, sz=2.2, sw=-0.4, noise=0.20, z=10)
blob(0,-9.5,9.8, rx=5.5,ry=0.9,rz=0.7, n=200, b=(0.70,0.90), s=(1.8,2.8))

# Lower lip (lush and full)
llip = [(-6,-10.8),(-3.5,-12.2),(0,-12.8),(3.5,-12.2),(6,-10.8)]
arc(llip, 150, b=0.95, sz=2.5, sw=1.0, noise=0.20, z=10)
blob(0,-11.8,9.5, rx=5.5,ry=1.3,rz=0.9, n=280, b=(0.75,0.98), s=(2.0,3.5))

# Apply speech weights to lower lip particles
for m in molecules[-280:]:
    m[7] = round(max(0, 1.0*(1-abs(m[0])/5.8)), 3)

# Mouth corners (upturned slightly — slight smile)
blob(-6.8,-10,9.2, rx=1.0,ry=0.8,rz=0.6, n=50, b=(0.62,0.80), s=(1.5,2.4))
blob( 6.8,-10,9.2, rx=1.0,ry=0.8,rz=0.6, n=50, b=(0.62,0.80), s=(1.5,2.4))

# Jaw pull-down molecules for speech
blob(0,-14,9, rx=6,ry=1.2,rz=0.8, n=140, b=(0.40,0.62), s=(1.5,2.4))
for m in molecules[-140:]:
    m[7] = round(max(0, 0.75*(1-abs(m[0])/6.5)), 3)

# ── CHEEKS (warm soft glow) ──────────────────────────────────────────
blob(-13,3,7.5, rx=5,ry=4,rz=2.8, n=320, b=(0.50,0.78), s=(1.5,2.6))
blob( 13,3,7.5, rx=5,ry=4,rz=2.8, n=320, b=(0.50,0.78), s=(1.5,2.6))

# ── JAWLINE ──────────────────────────────────────────────────────────
arc([(-15,-5),(-14,-11),(-12,-18),(-8,-23),(-2,-26)], 90, b=0.60, sz=1.8, noise=0.42, z=5)
arc([( 15,-5),( 14,-11),( 12,-18),( 8,-23),( 2,-26)], 90, b=0.60, sz=1.8, noise=0.42, z=5)
blob(0,-26,6, rx=4,ry=2.5,rz=1.8, n=170, b=(0.50,0.72), s=(1.5,2.5))

# ── NECK (natural column) ────────────────────────────────────────────
blob(0,-33,3, rx=8,ry=6,rz=4, n=380, b=(0.28,0.52), s=(1.2,2.2))
arc([(-12,-41),(-6,-44),(0,-45),(6,-44),(12,-41)], 65, b=0.42, sz=1.5, noise=0.5, z=2)

# ── EAR HINTS (tiny, not horns) ──────────────────────────────────────
blob(-16.5,7,0, rx=2.2,ry=3.5,rz=1.2, n=60, b=(0.35,0.55), s=(1.3,2.0))
blob( 16.5,7,0, rx=2.2,ry=3.5,rz=1.2, n=60, b=(0.35,0.55), s=(1.3,2.0))

# ── FLOATING STAR FIELD ──────────────────────────────────────────────
for _ in range(450):
    a = random.uniform(0, 2*math.pi)
    d = random.uniform(22,42)
    ax = math.cos(a)*d*random.uniform(0.7,1.1)
    ay = math.sin(a)*d*random.uniform(0.5,0.9)+2
    az = random.uniform(-18,-5)
    pt(ax,ay,az, random.uniform(0.08,0.35), random.uniform(1.0,2.0))

# ── BIG BRIGHT CONSTELLATION STAR NODES (golden flare dots) ─────────
for _ in range(220):
    hx = random.gauss(0,9)
    hy = random.gauss(2,13)
    hz = random.uniform(8,13)
    if abs(hx)<17 and -27<hy<30:
        pt(hx, hy, hz, random.uniform(0.90,1.0), random.uniform(2.5,4.0))

print(f"Total molecules: {len(molecules)}")
with open('zohra/api/static/zohra_organic_molecules.json','w') as f:
    json.dump({'molecules':molecules}, f, cls=E)
print("Saved!")
