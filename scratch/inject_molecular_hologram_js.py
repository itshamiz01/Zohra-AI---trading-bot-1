import re

with open('scratch/build_gold_command_center.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Replace voice waveform and add molecular hologram initialization
old_waveform = '''        // ─── GOLDEN VOICE WAVEFORM SIMULATOR / MIC ───
        function initVoiceWaveform() {
            const canvas = document.getElementById('voice-canvas');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            let t = 0;

            function drawWave() {
                requestAnimationFrame(drawWave);
                t += 0.05;
                const w = canvas.width = canvas.clientWidth;
                const h = canvas.height = canvas.clientHeight;
                ctx.clearRect(0, 0, w, h);

                ctx.lineWidth = 1.5;
                ctx.strokeStyle = '#ffd700';
                ctx.shadowColor = 'rgba(212, 175, 55, 0.4)';
                ctx.shadowBlur = 8;
                ctx.beginPath();

                const bars = 48;
                const barWidth = w / bars;
                for (let i = 0; i < bars; i++) {
                    const distFromCenter = Math.abs(i - bars / 2) / (bars / 2);
                    const envelope = Math.cos(distFromCenter * Math.PI * 0.5);
                    const amp = isListening ? (Math.sin(t * 2 + i * 0.4) * 0.5 + 0.5) * 16 * envelope : 2;
                    
                    const x = i * barWidth + barWidth * 0.5;
                    const y1 = h * 0.5 - amp;
                    const y2 = h * 0.5 + amp;
                    ctx.moveTo(x, y1);
                    ctx.lineTo(x, y2);
                }
                ctx.stroke();
            }
            drawWave();
        }

        function toggleVoiceCapture() {
            isListening = !isListening;
            const el = document.getElementById('voice-status-txt');
            if (el) el.textContent = isListening ? 'Listening... (Click to mute)' : 'Microphone Muted (Click to talk)';
        }'''

new_hologram_js = '''        // ─── ZOHRA 3D MOLECULAR HOLOGRAM ENGINE ───
        let holoScene, holoCamera, holoRenderer, holoGroup;
        let holoPointsGeometry, holoPositionsAttr, holoBasePositions, holoRegions;
        let holoPointsCount = 0;
        let isHoloSpeaking = false;
        let holoMouthOpen = 0;
        let holoTargetMouthOpen = 0;
        let holoAudioIntensity = 0;
        let holoAudioCtx = null;
        let holoAnalyser = null;
        let holoFreqData = null;
        let holoMouseX = 0, holoMouseY = 0;

        // Custom golden particle texture
        function createHoloParticleTexture() {
            const canvas = document.createElement('canvas');
            canvas.width = 64;
            canvas.height = 64;
            const ctx = canvas.getContext('2d');
            const grad = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
            grad.addColorStop(0, 'rgba(255, 255, 255, 1.0)');
            grad.addColorStop(0.18, 'rgba(255, 235, 140, 0.95)');
            grad.addColorStop(0.45, 'rgba(212, 175, 55, 0.45)');
            grad.addColorStop(1, 'rgba(212, 175, 55, 0)');
            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.arc(32, 32, 32, 0, Math.PI * 2);
            ctx.fill();
            return new THREE.CanvasTexture(canvas);
        }

        async function initZohraMolecularHologram() {
            const canvas = document.getElementById('zohra-hologram-canvas');
            if (!canvas || typeof THREE === 'undefined') return;

            holoScene = new THREE.Scene();
            holoCamera = new THREE.PerspectiveCamera(42, canvas.clientWidth / canvas.clientHeight, 1, 1000);
            holoCamera.position.set(0, 2, 195);

            holoRenderer = new THREE.WebGLRenderer({
                canvas: canvas,
                alpha: true,
                antialias: true,
                powerPreference: 'high-performance'
            });
            holoRenderer.setSize(canvas.clientWidth, canvas.clientHeight);
            holoRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

            holoGroup = new THREE.Group();
            holoScene.add(holoGroup);

            // Load precomputed 3D facial molecule points
            try {
                const res = await fetch('/static/zohra_face_molecules.json');
                if (!res.ok) throw new Error('Could not load molecules JSON');
                const data = await res.json();
                holoPointsCount = data.length;

                holoPointsGeometry = new THREE.BufferGeometry();
                const positions = new Float32Array(holoPointsCount * 3);
                holoBasePositions = new Float32Array(holoPointsCount * 3);
                const colors = new Float32Array(holoPointsCount * 3);
                holoRegions = new Uint8Array(holoPointsCount);

                for (let i = 0; i < holoPointsCount; i++) {
                    const p = data[i]; // [nx, ny, z, r, g, b, size, region]
                    positions[i * 3] = p[0];
                    positions[i * 3 + 1] = p[1];
                    positions[i * 3 + 2] = p[2];

                    holoBasePositions[i * 3] = p[0];
                    holoBasePositions[i * 3 + 1] = p[1];
                    holoBasePositions[i * 3 + 2] = p[2];

                    colors[i * 3] = p[3] / 255.0;
                    colors[i * 3 + 1] = p[4] / 255.0;
                    colors[i * 3 + 2] = p[5] / 255.0;

                    holoRegions[i] = p[7];
                }

                holoPositionsAttr = new THREE.BufferAttribute(positions, 3);
                holoPointsGeometry.setAttribute('position', holoPositionsAttr);
                holoPointsGeometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

                // Golden Glowing Particle Material
                const particleMat = new THREE.PointsMaterial({
                    size: 2.5,
                    map: createHoloParticleTexture(),
                    vertexColors: true,
                    transparent: true,
                    blending: THREE.AdditiveBlending,
                    depthWrite: false
                });

                const pointCloud = new THREE.Points(holoPointsGeometry, particleMat);
                holoGroup.add(pointCloud);

                // Add connecting molecular filaments (bonds) on face
                const lineIndices = [];
                for (let i = 0; i < holoPointsCount; i += 3) {
                    for (let j = i + 1; j < Math.min(holoPointsCount, i + 8); j++) {
                        const dx = holoBasePositions[i * 3] - holoBasePositions[j * 3];
                        const dy = holoBasePositions[i * 3 + 1] - holoBasePositions[j * 3 + 1];
                        const dz = holoBasePositions[i * 3 + 2] - holoBasePositions[j * 3 + 2];
                        const d = Math.sqrt(dx*dx + dy*dy + dz*dz);
                        if (d > 1.2 && d < 4.2) {
                            lineIndices.push(i, j);
                        }
                    }
                }
                const lineGeo = new THREE.BufferGeometry();
                lineGeo.setAttribute('position', holoPositionsAttr);
                lineGeo.setIndex(lineIndices);
                const lineMat = new THREE.LineBasicMaterial({
                    color: 0xd4af37,
                    transparent: true,
                    opacity: 0.16,
                    blending: THREE.AdditiveBlending
                });
                const lineSegments = new THREE.LineSegments(lineGeo, lineMat);
                holoGroup.add(lineSegments);

                console.log(`✅ Zohra 3D Molecular Hologram loaded: ${holoPointsCount} nodes and ${lineIndices.length / 2} bonds.`);
            } catch (err) {
                console.error("Hologram load error:", err);
            }

            // Mouse interaction for 3D parallax
            window.addEventListener('mousemove', (e) => {
                const rect = canvas.getBoundingClientRect();
                holoMouseX = ((e.clientX - rect.left) / rect.width) * 2 - 1;
                holoMouseY = -(((e.clientY - rect.top) / rect.height) * 2 - 1);
            });

            // Click hologram to trigger interactive talking speech demonstration
            canvas.addEventListener('click', () => {
                toggleTalkingDemo();
            });

            // Animation Loop
            let clock = new THREE.Clock();
            function renderHolo() {
                requestAnimationFrame(renderHolo);
                const t = clock.getElapsedTime();

                // 1. Audio and Speech Dynamics
                if (holoAnalyser && holoFreqData) {
                    holoAnalyser.getByteFrequencyData(holoFreqData);
                    let sum = 0;
                    for (let b = 2; b < 16; b++) sum += holoFreqData[b];
                    const vol = (sum / 14.0) / 128.0;
                    if (vol > 0.07) {
                        isHoloSpeaking = true;
                        holoAudioIntensity = Math.min(1.0, vol * 1.8);
                    } else if (!window._demoTalkingActive) {
                        holoAudioIntensity *= 0.88;
                        if (holoAudioIntensity < 0.02) isHoloSpeaking = false;
                    }
                }

                // Natural human speech phoneme cadence (~3.5 Hz base with syllable harmonics)
                if (isHoloSpeaking) {
                    const syllableWave = Math.sin(t * 15.0) * 0.5 + 0.5;
                    const phonemeVowel = Math.cos(t * 8.5) * 0.35 + 0.65;
                    holoTargetMouthOpen = syllableWave * phonemeVowel * Math.max(holoAudioIntensity, 0.6);
                } else {
                    holoTargetMouthOpen = 0;
                }
                holoMouthOpen += (holoTargetMouthOpen - holoMouthOpen) * 0.35;

                // 2. Point Deformations (Talking, Blinking, Breathing)
                if (holoPositionsAttr && holoBasePositions && holoRegions) {
                    const pos = holoPositionsAttr.array;
                    const count = holoPointsCount;

                    // Periodic natural eye blink every ~3.8 seconds
                    const blinkCycle = t % 4.0;
                    let blink = 0;
                    if (blinkCycle < 0.15) {
                        blink = Math.sin((blinkCycle / 0.15) * Math.PI);
                    }

                    for (let i = 0; i < count; i++) {
                        const reg = holoRegions[i];
                        const bx = holoBasePositions[i * 3];
                        const by = holoBasePositions[i * 3 + 1];
                        const bz = holoBasePositions[i * 3 + 2];

                        let dx = 0, dy = 0, dz = 0;

                        // Lower Lip: moves down & out dynamically with speech
                        if (reg === 2) {
                            const weight = Math.max(0, 1.0 - Math.abs(bx) / 24.0);
                            dy = -holoMouthOpen * 5.2 * weight;
                            dz = +holoMouthOpen * 2.4 * weight;
                        }
                        // Jaw & Chin: moves down with mouth opening
                        else if (reg === 3) {
                            dy = -holoMouthOpen * 3.2;
                            dz = -holoMouthOpen * 0.8;
                        }
                        // Upper Lip: raises slightly
                        else if (reg === 1) {
                            const weight = Math.max(0, 1.0 - Math.abs(bx) / 22.0);
                            dy = +holoMouthOpen * 1.5 * weight;
                            dz = +holoMouthOpen * 1.0 * weight;
                        }
                        // Eyelids: blink down
                        else if (reg === 4 || reg === 5) {
                            dy = -blink * 3.2;
                        }
                        // Curly hair: gentle cosmic breathing and floating
                        else if (reg === 7) {
                            dy = Math.sin(t * 1.6 + bx * 0.1) * 0.5;
                            dz = Math.cos(t * 1.4 + by * 0.1) * 0.6;
                        }

                        // Speech energy wave radiating outward from mouth
                        if (isHoloSpeaking) {
                            const distFromMouth = Math.sqrt(bx * bx + (by + 20) * (by + 20));
                            if (distFromMouth < 60) {
                                const ripple = Math.sin(distFromMouth * 0.2 - t * 10) * holoMouthOpen * 0.6;
                                dz += ripple;
                            }
                        }

                        pos[i * 3] = bx + dx;
                        pos[i * 3 + 1] = by + dy;
                        pos[i * 3 + 2] = bz + dz;
                    }
                    holoPositionsAttr.needsUpdate = true;
                }

                // 3. Head 3D Parallax & Subtle Organic Sway
                if (holoGroup) {
                    const breathe = 1.0 + Math.sin(t * 1.2) * 0.008;
                    holoGroup.scale.set(breathe, breathe, breathe);

                    holoGroup.rotation.y += ((holoMouseX * 0.22) - holoGroup.rotation.y) * 0.06;
                    holoGroup.rotation.x += ((-holoMouseY * 0.16) - holoGroup.rotation.x) * 0.06;
                    holoGroup.rotation.z = Math.sin(t * 0.8) * 0.015;
                }

                // 4. Update Status Pill
                const pillState = document.getElementById('holo-speech-state');
                if (pillState) {
                    if (isHoloSpeaking) {
                        pillState.textContent = 'HOLOGRAPHIC QUANTUM CORE // SPEAKING';
                        pillState.style.color = 'var(--gold-bright)';
                    } else if (isListening) {
                        pillState.textContent = 'HOLOGRAPHIC QUANTUM CORE // LISTENING';
                        pillState.style.color = 'var(--green-emerald)';
                    } else {
                        pillState.textContent = 'HOLOGRAPHIC QUANTUM CORE // IDLE';
                        pillState.style.color = 'var(--gold-light)';
                    }
                }

                holoRenderer.render(holoScene, holoCamera);
            }
            renderHolo();

            window.addEventListener('resize', () => {
                if (!canvas.clientWidth || !canvas.clientHeight) return;
                holoCamera.aspect = canvas.clientWidth / canvas.clientHeight;
                holoCamera.updateProjectionMatrix();
                holoRenderer.setSize(canvas.clientWidth, canvas.clientHeight);
            });
        }

        // Toggle demonstration of Zohra speaking
        window._demoTalkingActive = false;
        let demoSpeechTimeout = null;
        function toggleTalkingDemo(durationSec = 6) {
            window._demoTalkingActive = true;
            isHoloSpeaking = true;
            holoAudioIntensity = 0.85;

            // Optional Browser Speech Synthesis greeting
            if ('speechSynthesis' in window) {
                window.speechSynthesis.cancel();
                const utter = new SpeechSynthesisUtterance("Greetings Knight. Zohra neural core is active and ready for your command.");
                utter.rate = 1.05;
                utter.pitch = 1.15;
                utter.onend = () => {
                    window._demoTalkingActive = false;
                    isHoloSpeaking = false;
                    holoAudioIntensity = 0;
                };
                window.speechSynthesis.speak(utter);
            }

            clearTimeout(demoSpeechTimeout);
            demoSpeechTimeout = setTimeout(() => {
                window._demoTalkingActive = false;
                isHoloSpeaking = false;
                holoAudioIntensity = 0;
            }, durationSec * 1000);
        }

        // ─── GOLDEN VOICE WAVEFORM SIMULATOR & MIC HOOK ───
        async function connectMicrophoneStream() {
            try {
                if (!holoAudioCtx) {
                    holoAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
                }
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                const source = holoAudioCtx.createMediaStreamSource(stream);
                holoAnalyser = holoAudioCtx.createAnalyser();
                holoAnalyser.fftSize = 64;
                source.connect(holoAnalyser);
                holoFreqData = new Uint8Array(holoAnalyser.frequencyBinCount);
                console.log("🎤 Real microphone hooked directly to Zohra molecular hologram!");
                return true;
            } catch (err) {
                console.warn("Microphone permission or hardware not active:", err);
                return false;
            }
        }

        function initVoiceWaveform() {
            const canvas = document.getElementById('voice-canvas');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            let t = 0;

            function drawWave() {
                requestAnimationFrame(drawWave);
                t += 0.05;
                const w = canvas.width = canvas.clientWidth;
                const h = canvas.height = canvas.clientHeight;
                ctx.clearRect(0, 0, w, h);

                ctx.lineWidth = 1.5;
                ctx.strokeStyle = '#ffd700';
                ctx.shadowColor = 'rgba(212, 175, 55, 0.4)';
                ctx.shadowBlur = 8;
                ctx.beginPath();

                const bars = 48;
                const barWidth = w / bars;
                for (let i = 0; i < bars; i++) {
                    const distFromCenter = Math.abs(i - bars / 2) / (bars / 2);
                    const envelope = Math.cos(distFromCenter * Math.PI * 0.5);
                    const activeAmp = (isListening || isHoloSpeaking) ? (Math.sin(t * 2.5 + i * 0.4) * 0.5 + 0.5) * 18 * envelope : 2.5;
                    
                    const x = i * barWidth + barWidth * 0.5;
                    const y1 = h * 0.5 - activeAmp;
                    const y2 = h * 0.5 + activeAmp;
                    ctx.moveTo(x, y1);
                    ctx.lineTo(x, y2);
                }
                ctx.stroke();
            }
            drawWave();
        }

        async function toggleVoiceCapture() {
            isListening = !isListening;
            const el = document.getElementById('voice-status-txt');
            if (isListening) {
                if (el) el.textContent = 'Listening... (Talk now to move hologram)';
                await connectMicrophoneStream();
                // Also trigger conversational greeting
                toggleTalkingDemo(4);
            } else {
                if (el) el.textContent = 'Microphone Muted (Click to talk)';
                window._demoTalkingActive = false;
                isHoloSpeaking = false;
            }
        }'''

if old_waveform in code:
    code = code.replace(old_waveform, new_hologram_js)
    print("Voice waveform & hologram engine replaced successfully!")
else:
    print("old_waveform not found!")

# Also add initZohraMolecularHologram() to DOMContentLoaded
old_init = '''        // Init Sequence
        window.addEventListener('DOMContentLoaded', () => {
            initCelestialCanvas();
            initVoiceWaveform();'''

new_init = '''        // Init Sequence
        window.addEventListener('DOMContentLoaded', () => {
            initCelestialCanvas();
            initZohraMolecularHologram();
            initVoiceWaveform();'''

if old_init in code:
    code = code.replace(old_init, new_init)
    print("DOMContentLoaded init updated with initZohraMolecularHologram()!")
else:
    print("old_init not found!")

with open('scratch/build_gold_command_center.py', 'w', encoding='utf-8') as f:
    f.write(code)
