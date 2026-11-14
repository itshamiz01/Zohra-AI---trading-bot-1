import sys
sys.stdout.reconfigure(encoding='utf-8')

dashboard_path = "zohra/api/dashboard.html"
with open(dashboard_path, "r", encoding="utf-8") as f:
    text = f.read()

checks = [
    ("Three.js script", "three.min.js" in text),
    ("Avatar CSS styles", "zohra-avatar-widget" in text),
    ("Avatar widget in header", "zohra-avatar-orb" in text),
    ("Fleet Bar HTML", "fleet-bar-container" in text),
    ("Consensus Radar HTML", "consensus-radar-panel" in text),
    ("HIE Tab Button", "tab-hie" in text),
    ("HIE Tab Content", "content-hie" in text),
    ("Agent Swarm Bar", "agent-swarm-bar" in text),
    ("Holographic Face Modal", "zohra-face-modal" in text),
    ("Avatar JS logic", "generateFaceMolecularGeometry" in text),
    ("Fleet JS logic", "fetchFleetData" in text)
]

for name, status in checks:
    print(f"[{'OK' if status else 'MISSING'}] {name}")
