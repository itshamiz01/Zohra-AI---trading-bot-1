import sys

sys.stdout.reconfigure(encoding='utf-8')

# Search for June 23 logs between 15:50 and 16:15
for logfile in ["logs/zohra_brain_a.log", "logs/zohra_engine_a.log"]:
    print(f"\n==========================================")
    print(f"Log: {logfile}")
    print(f"==========================================")
    with open(logfile, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "2026-06-23" in line:
                # check if hour is 15 or 16
                if " 15:50" in line or " 15:51" in line or " 15:52" in line or " 15:53" in line or " 15:54" in line or " 15:55" in line or " 15:56" in line or " 15:57" in line or " 15:58" in line or " 15:59" in line or " 16:0" in line or " 16:10" in line or " 16:11" in line or " 16:12" in line:
                    print(line.strip())
