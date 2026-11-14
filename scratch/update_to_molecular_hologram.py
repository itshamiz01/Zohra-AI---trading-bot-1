import re

with open('scratch/build_gold_command_center.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Replace HTML: remove <img src="/static/zohra_portrait.png">
old_html = '''                <!-- Golden Front-Facing Holographic Portrait -->
                <div class="central-portrait-stage">
                    <img src="/static/zohra_portrait.png" alt="ZOHRA Holographic Portrait" class="portrait-img" id="zohra-portrait-img">
                </div>'''

new_html = '''                <!-- 3D Molecular Hologram Stage (Zero Direct Images) -->
                <div class="central-hologram-stage" id="zohra-hologram-stage">
                    <canvas id="zohra-hologram-canvas"></canvas>
                    <div class="hologram-status-pill" id="hologram-voice-indicator">
                        <span class="holo-dot"></span>
                        <span id="holo-speech-state">HOLOGRAPHIC QUANTUM CORE // IDLE</span>
                    </div>
                </div>'''

if old_html in content:
    content = content.replace(old_html, new_html)
    print("HTML stage replaced!")
else:
    print("old_html not found!")

# 2. Replace CSS for portrait with central-hologram-stage
old_portrait_css = '''        /* Central Holographic Portrait Asset */
        .central-portrait-stage {
            position: absolute;
            top: 45%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 620px;
            height: 480px;
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 5;
            pointer-events: none;
        }
        .portrait-img {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            filter: drop-shadow(0 0 35px rgba(212, 175, 55, 0.25));
            animation: portraitBreathe 6s ease-in-out infinite;
            transition: transform 0.1s ease-out;
        }
        @keyframes portraitBreathe {
            0%, 100% { transform: scale(1); filter: drop-shadow(0 0 30px rgba(212, 175, 55, 0.2)); }
            50% { transform: scale(1.015); filter: drop-shadow(0 0 45px rgba(212, 175, 55, 0.35)); }
        }'''

new_hologram_css = '''        /* 3D Molecular Hologram Stage */
        .central-hologram-stage {
            position: absolute;
            top: 46%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 680px;
            height: 520px;
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 5;
            pointer-events: auto;
        }
        #zohra-hologram-canvas {
            width: 100%;
            height: 100%;
            display: block;
        }
        .hologram-status-pill {
            position: absolute;
            bottom: 6px;
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(10, 12, 18, 0.88);
            border: 1px solid var(--gold-border);
            border-radius: 20px;
            padding: 4px 14px;
            font-size: 9px;
            letter-spacing: 2px;
            color: var(--gold-light);
            text-transform: uppercase;
            box-shadow: 0 0 15px rgba(212, 175, 55, 0.12);
            pointer-events: none;
        }
        .holo-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--gold-bright);
            box-shadow: 0 0 8px var(--gold-bright);
            animation: holoDotPulse 1.8s infinite ease-in-out;
        }
        @keyframes holoDotPulse {
            0%, 100% { transform: scale(0.9); opacity: 0.6; }
            50% { transform: scale(1.3); opacity: 1.0; }
        }'''

if old_portrait_css in content:
    content = content.replace(old_portrait_css, new_hologram_css)
    print("Portrait CSS replaced with hologram CSS!")
else:
    print("old_portrait_css not found!")

with open('scratch/build_gold_command_center.py', 'w', encoding='utf-8') as f:
    f.write(content)
