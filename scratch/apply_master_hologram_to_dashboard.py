import re

with open('scratch/build_gold_command_center.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Update Hologram Stage CSS to make it larger and centered
old_stage_css = '''        /* 3D Molecular Hologram Stage */
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
        }'''

new_stage_css = '''        /* 3D Molecular Hologram Stage - Large & Prominent */
        .central-hologram-stage {
            position: absolute;
            top: 44%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 820px;
            height: 620px;
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 5;
            pointer-events: auto;
        }'''

if old_stage_css in code:
    code = code.replace(old_stage_css, new_stage_css)
    print("Stage CSS updated to large size!")
else:
    print("old_stage_css not found!")

# 2. Add an interactive Talk button in the hologram stage status pill
old_pill_html = '''                    <div class="hologram-status-pill" id="hologram-voice-indicator">
                        <span class="holo-dot"></span>
                        <span id="holo-speech-state">HOLOGRAPHIC QUANTUM CORE // IDLE</span>
                    </div>'''

new_pill_html = '''                    <div class="hologram-status-pill" id="hologram-voice-indicator" style="pointer-events: auto; cursor: pointer;" onclick="toggleTalkingDemo(5)" title="Click to talk with Zohra">
                        <span class="holo-dot"></span>
                        <span id="holo-speech-state">HOLOGRAPHIC QUANTUM CORE // IDLE</span>
                        <span style="border-left: 1px solid rgba(212,175,55,0.3); padding-left: 8px; color: var(--gold-bright); font-weight: 700;">[ CLICK TO TALK ]</span>
                    </div>'''

if old_pill_html in code:
    code = code.replace(old_pill_html, new_pill_html)
    print("Pill HTML updated with interactive talk button!")
else:
    print("old_pill_html not found!")

# 3. Replace the hologram JS with the photorealistic molecular mesh + mouth articulation engine
hologram_js_pattern = re.compile(
    r'// ─── ZOHRA 3D MOLECULAR HOLOGRAM ENGINE ───.*?// ─── GOLDEN VOICE WAVEFORM SIMULATOR',
    re.DOTALL
)

master_hologram_engine = '''// ─── ZOHRA REAL MOLECULAR HOLOGRAM ENGINE ───
        let holoScene, holoCamera, holoRenderer;
        let holoFaceMesh, holoPosAttr, holoBasePos;
        let holoPointCloud, holoLines;
        let holoMouthOpen = 0;
        let holoTargetMouthOpen = 0;
        let isHoloSpeaking = false;
        let isMicHooked = false;
        let holoAudioAnalyser = null;
        let holoFreqData = null;
        let holoDemoActive = false;
        let holoDemoTimeout = null;

        const MOUTH_CENTER_Y = -9.8;
        const CHIN_CENTER_Y = -23.0;

        function initZohraMolecularHologram() {
            const canvas = document.getElementById('zohra-hologram-canvas');
            if (!canvas || typeof THREE === 'undefined') return;

            holoScene = new THREE.Scene();
            // Camera distance: 142 gives a large, striking, crystal-clear face!
            holoCamera = new THREE.PerspectiveCamera(40, canvas.clientWidth / canvas.clientHeight, 1, 1000);
            holoCamera.position.set(0, 1.5, 142);

            holoRenderer = new THREE.WebGLRenderer({
                canvas: canvas,
                alpha: true,
                antialias: true,
                powerPreference: 'high-performance'
            });
            holoRenderer.setSize(canvas.clientWidth, canvas.clientHeight);
            holoRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

            // 1. Dark inner mouth cavity
            const cavityGeo = new THREE.PlaneGeometry(24, 14);
            const cavityMat = new THREE.MeshBasicMaterial({ color: 0x050302 });
            const mouthCavity = new THREE.Mesh(cavityGeo, cavityMat);
            mouthCavity.position.set(0, -9.5, -0.6);
            holoScene.add(mouthCavity);

            // 2. High-definition face plane geometry: 150 x 121 units, 90x90 segments
            const textureLoader = new THREE.TextureLoader();
            textureLoader.load('/static/zohra_face_master.png', (texture) => {
                texture.generateMipmaps = true;
                texture.minFilter = THREE.LinearMipmapLinearFilter;
                texture.magFilter = THREE.LinearFilter;

                const geo = new THREE.PlaneGeometry(150, 121, 90, 90);
                holoPosAttr = geo.attributes.position;
                holoBasePos = new Float32Array(holoPosAttr.array.length);
                holoBasePos.set(holoPosAttr.array);

                const mat = new THREE.MeshBasicMaterial({
                    map: texture,
                    transparent: true,
                    opacity: 0.98
                });

                holoFaceMesh = new THREE.Mesh(geo, mat);
                holoScene.add(holoFaceMesh);

                // 3. Golden constellation molecular nodes & bonds
                fetch('/static/zohra_master_nodes.json').then(r => r.json()).then(nodes => {
                    const nodeCount = nodes.length;
                    const nodeGeo = new THREE.BufferGeometry();
                    const nodePos = new Float32Array(nodeCount * 3);
                    const nodeBase = new Float32Array(nodeCount * 3);
                    const nodeCols = new Float32Array(nodeCount * 3);

                    for (let i = 0; i < nodeCount; i++) {
                        const n = nodes[i];
                        nodePos[i * 3] = n[0];
                        nodePos[i * 3 + 1] = n[1];
                        nodePos[i * 3 + 2] = 0.5;

                        nodeBase[i * 3] = n[0];
                        nodeBase[i * 3 + 1] = n[1];
                        nodeBase[i * 3 + 2] = 0.5;

                        nodeCols[i * 3] = n[2] / 255;
                        nodeCols[i * 3 + 1] = n[3] / 255;
                        nodeCols[i * 3 + 2] = n[4] / 255;
                    }

                    nodeGeo.setAttribute('position', new THREE.BufferAttribute(nodePos, 3));
                    nodeGeo.setAttribute('color', new THREE.BufferAttribute(nodeCols, 3));

                    // Glowing golden star sprite
                    const starCanvas = document.createElement('canvas');
                    starCanvas.width = starCanvas.height = 32;
                    const sctx = starCanvas.getContext('2d');
                    const sgrad = sctx.createRadialGradient(16, 16, 0, 16, 16, 16);
                    sgrad.addColorStop(0, '#ffffff');
                    sgrad.addColorStop(0.25, '#ffe57f');
                    sgrad.addColorStop(0.5, '#d4af37');
                    sgrad.addColorStop(1, 'transparent');
                    sctx.fillStyle = sgrad;
                    sctx.arc(16, 16, 16, 0, Math.PI * 2);
                    sctx.fill();
                    const starTex = new THREE.CanvasTexture(starCanvas);

                    holoPointCloud = new THREE.Points(nodeGeo, new THREE.PointsMaterial({
                        size: 4.6,
                        map: starTex,
                        vertexColors: true,
                        transparent: true,
                        blending: THREE.AdditiveBlending,
                        depthWrite: false
                    }));
                    holoScene.add(holoPointCloud);

                    // Connecting molecular bonds
                    const lineIndices = [];
                    for (let i = 0; i < nodeCount; i++) {
                        for (let j = i + 1; j < nodeCount; j++) {
                            const dx = nodeBase[i * 3] - nodeBase[j * 3];
                            const dy = nodeBase[i * 3 + 1] - nodeBase[j * 3 + 1];
                            const dist = Math.sqrt(dx*dx + dy*dy);
                            if (dist < 14) {
                                lineIndices.push(i, j);
                            }
                        }
                    }
                    const lineGeo = new THREE.BufferGeometry();
                    lineGeo.setAttribute('position', nodeGeo.attributes.position);
                    lineGeo.setIndex(lineIndices);
                    holoLines = new THREE.LineSegments(lineGeo, new THREE.LineBasicMaterial({
                        color: 0xd4af37,
                        transparent: true,
                        opacity: 0.26,
                        blending: THREE.AdditiveBlending
                    }));
                    holoScene.add(holoLines);
                });

                console.log("✅ Crystal-clear Zohra master face & molecular constellation initialized!");
            });

            // Click canvas to trigger voice interaction
            canvas.addEventListener('click', () => {
                toggleTalkingDemo(5);
            });

            // Animation loop
            let clock = new THREE.Clock();
            function render() {
                requestAnimationFrame(render);
                const t = clock.getElapsedTime();

                // 1. Audio and talking detection
                if (holoAudioAnalyser && holoFreqData) {
                    holoAudioAnalyser.getByteFrequencyData(holoFreqData);
                    let sum = 0;
                    for (let i = 2; i < 16; i++) sum += holoFreqData[i];
                    const vol = (sum / 14) / 128.0;
                    if (vol > 0.08) {
                        isHoloSpeaking = true;
                        const phoneme = Math.sin(t * 16.0) * 0.4 + 0.6;
                        holoTargetMouthOpen = Math.min(1.0, vol * 2.0) * phoneme;
                    } else if (!holoDemoActive) {
                        isHoloSpeaking = false;
                        holoTargetMouthOpen = 0;
                    }
                } else if (holoDemoActive) {
                    // Natural talking syllable cadence (~3.5 Hz)
                    const syllable = Math.sin(t * 14.5) * 0.5 + 0.5;
                    const vowel = Math.cos(t * 8.5) * 0.35 + 0.65;
                    holoTargetMouthOpen = syllable * vowel;
                } else {
                    holoTargetMouthOpen = 0;
                }

                // Smooth mouth interpolation
                holoMouthOpen += (holoTargetMouthOpen - holoMouthOpen) * 0.35;

                // 2. ONLY deform vertices when talking (remains 100% still when quiet)
                if (holoPosAttr && holoBasePos) {
                    if (holoMouthOpen > 0.002 || Math.abs(holoTargetMouthOpen - holoMouthOpen) > 0.002) {
                        const pos = holoPosAttr.array;
                        const vCount = pos.length / 3;

                        for (let i = 0; i < vCount; i++) {
                            const bx = holoBasePos[i * 3];
                            const by = holoBasePos[i * 3 + 1];

                            const dx = Math.abs(bx);
                            if (dx < 28) {
                                const horizWeight = Math.cos((dx / 28) * Math.PI * 0.5) ** 1.5;

                                // Lower lip & chin (moves downward and forward as mouth opens)
                                if (by <= MOUTH_CENTER_Y) {
                                    const distLowerLip = Math.abs(by - (MOUTH_CENTER_Y - 3.5));
                                    const lowerWeight = Math.exp(-(distLowerLip * distLowerLip) / 35.0);

                                    const distChin = Math.abs(by - CHIN_CENTER_Y);
                                    const chinWeight = Math.exp(-(distChin * distChin) / 80.0);

                                    const dy = -(lowerWeight * 7.2 + chinWeight * 4.0) * horizWeight * holoMouthOpen;
                                    pos[i * 3 + 1] = by + dy;
                                }
                                // Upper lip (arches slightly upward)
                                else if (by > MOUTH_CENTER_Y && by < MOUTH_CENTER_Y + 12) {
                                    const distUpperLip = Math.abs(by - (MOUTH_CENTER_Y + 2.5));
                                    const upperWeight = Math.exp(-(distUpperLip * distUpperLip) / 22.0);

                                    const dy = +(upperWeight * 1.8) * horizWeight * holoMouthOpen;
                                    pos[i * 3 + 1] = by + dy;
                                } else {
                                    pos[i * 3 + 1] = by;
                                }
                            } else {
                                pos[i * 3 + 1] = by;
                            }
                        }
                        holoPosAttr.needsUpdate = true;
                    }
                }

                // 3. Update status pill
                const pillState = document.getElementById('holo-speech-state');
                if (pillState) {
                    if (isHoloSpeaking || holoDemoActive) {
                        pillState.textContent = 'HOLOGRAPHIC QUANTUM CORE // SPEAKING';
                        pillState.style.color = 'var(--gold-bright)';
                    } else if (isMicHooked) {
                        pillState.textContent = 'HOLOGRAPHIC QUANTUM CORE // LISTENING';
                        pillState.style.color = 'var(--green-emerald)';
                    } else {
                        pillState.textContent = 'HOLOGRAPHIC QUANTUM CORE // IDLE';
                        pillState.style.color = 'var(--gold-light)';
                    }
                }

                holoRenderer.render(holoScene, holoCamera);
            }
            render();

            window.addEventListener('resize', () => {
                if (!canvas.clientWidth || !canvas.clientHeight) return;
                holoCamera.aspect = canvas.clientWidth / canvas.clientHeight;
                holoCamera.updateProjectionMatrix();
                holoRenderer.setSize(canvas.clientWidth, canvas.clientHeight);
            });
        }

        function toggleTalkingDemo(durationSec = 5) {
            holoDemoActive = true;
            isHoloSpeaking = true;

            if ('speechSynthesis' in window) {
                window.speechSynthesis.cancel();
                const utter = new SpeechSynthesisUtterance("Knight, all trading divisions and molecular intelligence circuits are active and synchronized.");
                utter.rate = 1.05;
                utter.pitch = 1.15;
                utter.onend = () => {
                    holoDemoActive = false;
                    isHoloSpeaking = false;
                };
                window.speechSynthesis.speak(utter);
            }

            clearTimeout(holoDemoTimeout);
            holoDemoTimeout = setTimeout(() => {
                holoDemoActive = false;
                isHoloSpeaking = false;
            }, durationSec * 1000);
        }

        // ─── GOLDEN VOICE WAVEFORM SIMULATOR'''

if hologram_js_pattern.search(code):
    code = hologram_js_pattern.sub(master_hologram_engine, code)
    print("Master hologram engine successfully substituted!")
else:
    print("hologram_js_pattern not matched!")

with open('scratch/build_gold_command_center.py', 'w', encoding='utf-8') as f:
    f.write(code)
