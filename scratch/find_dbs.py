import os

for root, dirs, files in os.walk('.'):
    for file in files:
        if file.endswith('.db'):
            path = os.path.join(root, file)
            print(f"DB file: {path} | Size: {os.path.getsize(path)} bytes")
