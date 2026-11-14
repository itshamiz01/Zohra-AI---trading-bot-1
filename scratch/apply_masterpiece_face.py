import re

def apply_masterpiece():
    src_file = 'scratch/build_gold_command_center.py'
    with open(src_file, 'r', encoding='utf-8') as f:
        content = f.read()

    new_hologram_js = '''        // ─── ZOHRA 100% PURE FLOATING CONSTELLATION MOLECULAR FACE ───
        let holoScene = null, holoCamera = null, holoRenderer = null;
        let holoMoleculesGeo = null;
        let holoBasePos = null;
        let holoCurPos = null;
        let holoSpeechWeights = null;
        let holoPhases = null;
        let holoPointCloud = null;
        let holoLines = null;
        let holoMoleculesCount = 0;
        let holoMouthOpen = 0;
        let holoTargetMouthOpen = 0;
        let isHoloSpeaking = false;
        let isMicHooked = false;
        let holoAudioAnalyser = null;
        let holoFreqData = null;
        let holoDemoActive = false;
        let holoDemoTimeout = null;

        function initZohraMolecularHologram() {
            const canvas = document.getElementById('zohra-hologram-canvas');
            if (!canvas || typeof THREE === 'undefined') return;

            holoScene = new THREE.Scene();
            // Camera positioned at 116 units: makes the face LARGER, majestic, filling the center stage!
            holoCamera = new THREE.PerspectiveCamera(40, canvas.clientWidth / canvas.clientHeight, 1, 1000);
            holoCamera.position.set(0, 0, 116);

            holoRenderer = new THREE.WebGLRenderer({
                canvas: canvas,
                alpha: true,
                antialias: true,
                powerPreference: 'high-performance'
            });
            holoRenderer.setSize(canvas.clientWidth, canvas.clientHeight);
            holoRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

            // Radiant golden molecule sprite with brilliant white-gold core
            const atomCanvas = document.createElement('canvas');
            atomCanvas.width = atomCanvas.height = 64;
            const actx = atomCanvas.getContext('2d');
            const grad = actx.createRadialGradient(32, 32, 0, 32, 32, 32);
            grad.addColorStop(0, '#ffffff');                     // Nuclear core
            grad.addColorStop(0.2, '#fff6c2');                   // Inner halo
            grad.addColorStop(0.46, '#ffd700');                  // Golden mantle
            grad.addColorStop(0.76, 'rgba(212, 175, 55, 0.42)'); // Amber corona
            grad.addColorStop(1, 'rgba(212, 175, 55, 0)');       // Falloff
            actx.fillStyle = grad;
            actx.beginPath();
            actx.arc(32, 32, 32, 0, Math.PI * 2);
            actx.fill();
            const atomTex = new THREE.CanvasTexture(atomCanvas);

            // Fetch the organic floating molecular face dataset (27,190 points directly from user_ref_2.jpg)
            fetch('/static/zohra_organic_molecules.json')
                .then(res => res.json())
                .then(data => {
                    const molecules = data.molecules;
                    holoMoleculesCount = molecules.length;
                    const N = holoMoleculesCount;

                    holoBasePos = new Float32Array(N * 3);
                    holoCurPos = new Float32Array(N * 3);
                    const colors = new Float32Array(N * 3);
                    holoSpeechWeights = new Float32Array(N);
                    holoPhases = new Float32Array(N);

                    for (let i = 0; i < N; i++) {
                        const m = molecules[i];
                        // m: [wx, wy, wz, r, g, b, size, speech_weight, phase]
                        holoBasePos[i * 3]     = m[0];
                        holoBasePos[i * 3 + 1] = m[1];
                        holoBasePos[i * 3 + 2] = m[2];

                        holoCurPos[i * 3]     = m[0];
                        holoCurPos[i * 3 + 1] = m[1];
                        holoCurPos[i * 3 + 2] = m[2];

                        colors[i * 3]     = m[3] / 255;
                        colors[i * 3 + 1] = m[4] / 255;
                        colors[i * 3 + 2] = m[5] / 255;

                        holoSpeechWeights[i] = m[7];
                        holoPhases[i] = m[8];
                    }

                    holoMoleculesGeo = new THREE.BufferGeometry();
                    holoMoleculesGeo.setAttribute('position', new THREE.BufferAttribute(holoCurPos, 3));
                    holoMoleculesGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3));

                    const pointsMat = new THREE.PointsMaterial({
                        size: 3.1,
                        map: atomTex,
                        vertexColors: true,
                        transparent: true,
                        blending: THREE.AdditiveBlending,
                        depthWrite: false
                    });

                    holoPointCloud = new THREE.Points(holoMoleculesGeo, pointsMat);
                    holoScene.add(holoPointCloud);

                    // Build golden cybernetic constellation bonds connecting nearby nodes
                    const lineIndices = [];
                    const step = 8;
                    for (let i = 0; i < N; i += step) {
                        const x1 = holoBasePos[i * 3];
                        const y1 = holoBasePos[i * 3 + 1];
                        const z1 = holoBasePos[i * 3 + 2];

                        let connections = 0;
                        for (let j = i + step; j < Math.min(N, i + 140); j += step) {
                            const dx = x1 - holoBasePos[j * 3];
                            const dy = y1 - holoBasePos[j * 3 + 1];
                            const dz = z1 - holoBasePos[j * 3 + 2];
                            const dist = Math.sqrt(dx*dx + dy*dy + dz*dz);
                            if (dist < 7.5) {
                                lineIndices.push(i, j);
                                connections++;
                                if (connections >= 2) break;
                            }
                        }
                    }

                    const linesGeo = new THREE.BufferGeometry();
                    linesGeo.setAttribute('position', holoMoleculesGeo.attributes.position);
                    linesGeo.setIndex(lineIndices);

                    holoLines = new THREE.LineSegments(linesGeo, new THREE.LineBasicMaterial({
                        color: 0xffd700,
                        transparent: true,
                        opacity: 0.22,
                        blending: THREE.AdditiveBlending
                    }));
                    holoScene.add(holoLines);

                    console.log(`🌌 Zohra Real Girl Constellation Hologram loaded with ${N} molecules & ${lineIndices.length / 2} lattice bonds!`);
                });

            // Click canvas to trigger voice interaction
            canvas.addEventListener('click', () => {
                toggleTalkingDemo(5);
            });

            // Animation loop with 3D Floating Physics
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
                    if (vol > 0.07) {
                        isHoloSpeaking = true;
                        const phoneme = Math.sin(t * 16.0) * 0.4 + 0.6;
                        holoTargetMouthOpen = Math.min(1.0, vol * 2.2) * phoneme;
                    } else if (!holoDemoActive) {
                        isHoloSpeaking = false;
                        holoTargetMouthOpen = 0;
                    }
                } else if (holoDemoActive) {
                    // Natural speech syllable cadence (~3.5 Hz)
                    const syllable = Math.sin(t * 14.0) * 0.5 + 0.5;
                    const vowel = Math.cos(t * 8.0) * 0.35 + 0.65;
                    holoTargetMouthOpen = syllable * vowel;
                } else {
                    holoTargetMouthOpen = 0;
                }

                // Smooth mouth interpolation
                holoMouthOpen += (holoTargetMouthOpen - holoMouthOpen) * 0.32;

                // 2. 3D Floating Physics & Speech Articulation ONLY when speaking
                if (holoMoleculesGeo && holoBasePos && holoCurPos) {
                    const pos = holoMoleculesGeo.attributes.position.array;
                    const N = holoMoleculesCount;
                    const mouthOpen = holoMouthOpen;

                    for (let i = 0; i < N; i++) {
                        const bx = holoBasePos[i * 3];
                        const by = holoBasePos[i * 3 + 1];
                        const bz = holoBasePos[i * 3 + 2];
                        const spkWeight = holoSpeechWeights[i];
                        const ph = holoPhases[i];

                        // Organic 3D Floating Drift
                        const fx = Math.sin(t * 0.85 + ph) * 0.7;
                        const fy = Math.cos(t * 0.75 + by * 0.04) * 0.85;
                        const fz = Math.sin(t * 0.8 + bx * 0.04) * 0.75;

                        // Speech Movement: ONLY when speaking (mouthOpen > 0)
                        let spkY = 0, spkZ = 0;
                        if (mouthOpen > 0.002 && Math.abs(spkWeight) > 0.01) {
                            if (spkWeight > 0) {
                                // Lower lip & jaw: move downward and forward
                                spkY = -mouthOpen * 7.5 * spkWeight;
                                spkZ = mouthOpen * 2.2 * spkWeight;
                            } else {
                                // Upper lip: arch slightly upward
                                spkY = -mouthOpen * 2.2 * spkWeight;
                                spkZ = -mouthOpen * 0.6 * spkWeight;
                            }
                        }

                        pos[i * 3]     = bx + fx;
                        pos[i * 3 + 1] = by + fy + spkY;
                        pos[i * 3 + 2] = bz + fz + spkZ;
                    }

                    holoMoleculesGeo.attributes.position.needsUpdate = true;
                }

                // 3. Whole-head gentle floating levitation
                if (holoPointCloud) {
                    holoPointCloud.position.y = Math.sin(t * 0.6) * 1.5;
                    holoPointCloud.position.x = Math.cos(t * 0.45) * 0.8;
                    holoPointCloud.rotation.y = Math.sin(t * 0.3) * 0.04;
                }
                if (holoLines) {
                    holoLines.position.y = holoPointCloud.position.y;
                    holoLines.position.x = holoPointCloud.position.x;
                    holoLines.rotation.y = holoPointCloud.rotation.y;
                }

                // 4. Update status pill
                const pillState = document.getElementById('holo-speech-state');
                if (pillState) {
                    if (isHoloSpeaking || holoDemoActive) {
                        pillState.textContent = 'HOLOGRAPHIC QUANTUM CORE // SPEAKING';
                        pillState.style.color = 'var(--gold-bright)';
                    } else if (isMicHooked) {
                        pillState.textContent = 'HOLOGRAPHIC QUANTUM CORE // LISTENING';
                        pillState.style.color = 'var(--green-emerald)';
                    } else {
                        pillState.textContent = 'HOLOGRAPHIC QUANTUM CORE // IDLE (FLOATING)';
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
        }'''

    # Replace from `// ─── 100% PURE 3D FLOATING MOLECULAR FACE ENGINE` or `let holoScene = null;` up to `function toggleTalkingDemo(durationSec = 25)`
    start_idx = content.find('let holoScene = null')
    if start_idx == -1:
        start_idx = content.find('// ─── 100% PURE 3D FLOATING MOLECULAR FACE ENGINE')
    
    end_idx = content.find('function toggleTalkingDemo(durationSec = 25)')
    
    if start_idx != -1 and end_idx != -1:
        new_content = content[:start_idx] + new_hologram_js + '\n\n        ' + content[end_idx:]
        with open(src_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("Updated scratch/build_gold_command_center.py successfully!")
    else:
        print(f"Could not find indices: start={start_idx}, end={end_idx}")

if __name__ == '__main__':
    apply_masterpiece()
