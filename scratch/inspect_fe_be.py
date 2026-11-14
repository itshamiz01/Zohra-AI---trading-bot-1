import os
import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

dashboard_path = "zohra/api/dashboard.html"
living_dashboard_path = "zohra/api/living-dashboard.html"

def analyze_html(path):
    if not os.path.exists(path):
        return
    print(f"=== Analyzing {path} ===")
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    print(f"File size: {len(text):,} chars, {len(text.splitlines()):,} lines")
    
    # switchTab targets
    switches = re.findall(r"switchTab\(['\"](.*?)['\"]\)", text)
    print(f"switchTab targets: {set(switches)}")
    
    # tab titles / navigation elements
    tab_matches = re.findall(r"<button[^>]*class=[\"'][^\"']*tab-btn[^\"']*[\"'][^>]*>(.*?)</button>", text, re.DOTALL)
    clean_tabs = [re.sub(r'<[^>]+>', '', t).strip() for t in tab_matches]
    print(f"Tab navigation buttons ({len(clean_tabs)}): {clean_tabs}")

    # fetch endpoints
    fetches = re.findall(r"fetch\((?:['\"`])([^'\"`\)\s\?]+)", text)
    unique_fetches = sorted(set(fetches))
    print(f"\nFetch API endpoints ({len(unique_fetches)}):")
    for ep in unique_fetches:
        print(f"  - {ep}")

    # major section IDs
    section_ids = re.findall(r"<section[^>]*id=[\"']([^\"']+)[\"']", text)
    div_tab_ids = re.findall(r"<div[^>]*class=[\"'][^\"']*tab-content[^\"']*[\"'][^>]*id=[\"']([^\"']+)[\"']", text)
    print(f"\nTab/Section container IDs:")
    print(f"  Sections: {section_ids}")
    print(f"  Tab containers: {div_tab_ids}")

analyze_html(dashboard_path)
print("\n" + "="*50 + "\n")
analyze_html(living_dashboard_path)
