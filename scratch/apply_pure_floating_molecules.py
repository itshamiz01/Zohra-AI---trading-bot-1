import re

def apply_pure_floating_molecular_face():
    src_file = 'scratch/build_gold_command_center.py'
    with open(src_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Define the new pure floating 3D molecular hologram implementation
    pure_molecules_js = '''        // ─── 100% PURE 3D FLOATING MOLECULAR FACE ENGINE (NO RASTER IMAGES) ───
        let holoMoleculesGeo = null;
        let holoBasePos = null;
        let holoCurPos = null;
        let holoRegions = null;
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
            // Perspective camera positioned to view the full floating molecular face
            holoCamera = new THREE.PerspectiveCamera(42, canvas.clientWidth / canvas.clientHeight, 1, 1000);
            holoCamera.position.set(0, 0, 160);

            holoRenderer = new THREE.WebGLRenderer({
                canvas: canvas,
                alpha: true,
                antialias: true,
                powerPreference: 'high-performance'
            });
            holoRenderer.setSize(canvas.clientWidth, canvas.clientHeight);
            holoRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

            // Generate radiant glowing molecular sprite
            const atomCanvas = document.createElement('canvas');
            atomCanvas.width = atomCanvas.height = 64;
            const actx = atomCanvas.getContext('2d');
            const grad = actx.createRadialGradient(32, 32, 0, 32, 32, 32);
            grad.addColorStop(0, '#ffffff');                     // Core nucleus: bright white
            grad.addColorStop(0.2, '#fff4b8');                   // Inner halo: warm white-gold
            grad.addColorStop(0.48, '#ffd700');                  // Mantle: vibrant gold
            grad.addColorStop(0.78, 'rgba(212, 175, 55, 0.45)'); // Outer corona: golden amber
            grad.addColorStop(1, 'rgba(212, 175, 55, 0)');       // Falloff: transparent
            actx.fillStyle = grad;
            actx.beginPath();
            actx.arc(32, 32, 32, 0, Math.PI * 2);
            actx.fill();
            const atomTex = new THREE.CanvasTexture(atomCanvas);

            // Fetch the high-density floating molecular face dataset (29,973 pure 3D molecules)
            fetch('/static/zohra_floating_molecules.json')
                .then(res => res.json())
                .then(molecules => {
                    holoMoleculesCount = molecules.length;
                    const N = holoMoleculesCount;

                    holoBasePos = new Float32Array(N * 3);
                    holoCurPos = new Float32Array(N * 3);
                    const colors = new Float32Array(N * 3);
                    holoRegions = new Int8Array(N);
                    holoPhases = new Float32Array(N);

                    for (let i = 0; i < N; i++) {
                        const m = molecules[i];
                        // m: [wx, wy, wz, r, g, b, size, region, phase]
                        holoBasePos[i * 3]     = m[0];
                        holoBasePos[i * 3 + 1] = m[1];
                        holoBasePos[i * 3 + 2] = m[2];

                        holoCurPos[i * 3]     = m[0];
                        holoCurPos[i * 3 + 1] = m[1];
                        holoCurPos[i * 3 + 2] = m[2];

                        colors[i * 3]     = m[3] / 255;
                        colors[i * 3 + 1] = m[4] / 255;
                        colors[i * 3 + 2] = m[5] / 255;

                        holoRegions[i] = m[7];
                        holoPhases[i] = m[8];
                    }

                    holoMoleculesGeo = new THREE.BufferGeometry();
                    holoMoleculesGeo.setAttribute('position', new THREE.BufferAttribute(holoCurPos, 3));
                    holoMoleculesGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3));

                    const pointsMat = new THREE.PointsMaterial({
                        size: 3.3,
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
                    const step = 6;
                    for (let i = 0; i < N; i += step) {
                        if (holoRegions[i] === 6) continue;
                        const x1 = holoBasePos[i * 3];
                        const y1 = holoBasePos[i * 3 + 1];
                        const z1 = holoBasePos[i * 3 + 2];

                        let connections = 0;
                        for (let j = i + step; j < Math.min(N, i + 160); j += step) {
                            if (holoRegions[j] === 6) continue;
                            const dx = x1 - holoBasePos[j * 3];
                            const dy = y1 - holoBasePos[j * 3 + 1];
                            const dz = z1 - holoBasePos[j * 3 + 2];
                            const dist = Math.sqrt(dx*dx + dy*dy + dz*dz);
                            if (dist < 8.5) {
                                lineIndices.push(i, j);
                                connections++;
                                if (connections >= 3) break;
                            }
                        }
                    }

                    const linesGeo = new THREE.BufferGeometry();
                    linesGeo.setAttribute('position', holoMoleculesGeo.attributes.position);
                    linesGeo.setIndex(lineIndices);

                    holoLines = new THREE.LineSegments(linesGeo, new THREE.LineBasicMaterial({
                        color: 0xffd700,
                        transparent: true,
                        opacity: 0.28,
                        blending: THREE.AdditiveBlending
                    }));
                    holoScene.add(holoLines);

                    console.log(`🌌 100% Pure Floating 3D Molecular Face initialized with ${N} golden molecules & ${lineIndices.length / 2} lattice bonds!`);
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
                    const syllable = Math.sin(t * 14.5) * 0.5 + 0.5;
                    const vowel = Math.cos(t * 8.5) * 0.35 + 0.65;
                    holoTargetMouthOpen = syllable * vowel;
                } else {
                    holoTargetMouthOpen = 0;
                }

                // Smooth mouth interpolation
                holoMouthOpen += (holoTargetMouthOpen - holoMouthOpen) * 0.35;

                // 2. 3D Floating Physics & Speech Articulation
                if (holoMoleculesGeo && holoBasePos && holoCurPos) {
                    const pos = holoMoleculesGeo.attributes.position.array;
                    const N = holoMoleculesCount;
                    const mouthOpen = holoMouthOpen;

                    for (let i = 0; i < N; i++) {
                        const bx = holoBasePos[i * 3];
                        const by = holoBasePos[i * 3 + 1];
                        const bz = holoBasePos[i * 3 + 2];
                        const reg = holoRegions[i];
                        const ph = holoPhases[i];

                        // Organic 3D Floating Drift
                        let fx = 0, fy = 0, fz = 0;
                        if (reg === 5) {
                            // Hair curls float with gentle zero-gravity harmonic waves
                            fx = Math.sin(t * 1.05 + ph) * 2.2;
                            fy = Math.cos(t * 0.82 + ph * 1.1) * 2.6;
                            fz = Math.sin(t * 0.95 + ph * 0.7) * 2.0;
                        } else if (reg === 6) {
                            // Ambient cosmic dust: floating brownian drift
                            fx = Math.sin(t * 0.45 + ph) * 3.8;
                            fy = Math.cos(t * 0.4 + ph) * 3.8;
                            fz = Math.sin(t * 0.55 + ph * 1.3) * 3.5;
                        } else if (reg === 4) {
                            // Eyes: stable gaze, very subtle floating micro-drift
                            fx = Math.sin(t * 0.65 + ph) * 0.25;
                            fy = Math.cos(t * 0.55 + ph) * 0.3;
                            fz = Math.sin(t * 0.45 + ph) * 0.2;
                        } else {
                            // Facial core / skin: subtle lifelike breathing floating wave
                            fx = Math.sin(t * 0.75 + ph) * 0.6;
                            fy = Math.cos(t * 0.7 + by * 0.04) * 0.9;
                            fz = Math.sin(t * 0.85 + bx * 0.04) * 0.7;
                        }

                        // Speech Articulation ONLY when speaking (mouthOpen > 0)
                        let spkX = 0, spkY = 0, spkZ = 0;
                        if (mouthOpen > 0.001) {
                            if (reg === 2) {
                                // Lower lip: opens downward and slightly forward
                                spkY = -mouthOpen * 7.5;
                                spkZ = mouthOpen * 2.2;
                            } else if (reg === 3) {
                                // Chin / jaw: drops naturally with lower lip
                                spkY = -mouthOpen * 4.8;
                                spkZ = mouthOpen * 1.4;
                            } else if (reg === 1) {
                                // Upper lip: arches slightly upward
                                spkY = mouthOpen * 2.0;
                                spkZ = mouthOpen * 0.5;
                            }
                        }

                        pos[i * 3]     = bx + fx + spkX;
                        pos[i * 3 + 1] = by + fy + spkY;
                        pos[i * 3 + 2] = bz + fz + spkZ;
                    }

                    holoMoleculesGeo.attributes.position.needsUpdate = true;
                }

                // 3. Gentle whole-head floating levitation & subtle mouse parallax
                if (holoPointCloud) {
                    holoPointCloud.position.y = Math.sin(t * 0.6) * 1.6;
                    holoPointCloud.position.x = Math.cos(t * 0.45) * 1.0;
                    holoPointCloud.rotation.y = Math.sin(t * 0.35) * 0.05;
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

    # Pattern matching from `let holoPosAttr = null;` or `let holoScene = null;` up to `function toggleTalkingDemo`
    pattern = re.compile(r'let holoScene = null;.*?function toggleTalkingDemo\(durationSec = 25\)', re.DOTALL)
    
    replacement = 'let holoScene = null;\n' + pure_molecules_js + '\n\n        function toggleTalkingDemo(durationSec = 25)'
    
    new_content, count = pattern.subn(replacement, content)
    if count == 0:
        print("Regex pattern not found, trying alternate anchor...")
        # Fallback search
        start_idx = content.find('let holoTargetMouthOpen = 0;')
        end_idx = content.find('function toggleTalkingDemo(durationSec = 25)')
        if start_idx != -1 and end_idx != -1:
            new_content = content[:start_idx] + pure_molecules_js + '\n\n        ' + content[end_idx:]
            count = 1

    print(f"Replacement status: count={count}")
    if count > 0:
        with open(src_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {src_file} successfully!")
    else:
        print("Failed to replace in build_gold_command_center.py!")

if __name__ == '__main__':
    apply_pure_floating_molecular_face()
