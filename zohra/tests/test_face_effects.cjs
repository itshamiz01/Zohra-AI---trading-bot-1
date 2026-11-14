const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const effects = require('../api/static/face-effects.js');

const sampleRate = 48000;
const spectrum = () => new Uint8Array(1024);

test('three effects cycle in order', () => {
    assert.deepEqual(effects.MODES, ['Gather', 'Resonance', 'Gesture']);
    assert.equal(effects.nextMode(0), 1);
    assert.equal(effects.nextMode(1), 2);
    assert.equal(effects.nextMode(2), 0);
});

test('face and surroundings share a slow, continuous multicolour palette', () => {
    assert.notDeepEqual(effects.paletteAt(0), effects.paletteAt(9));
    assert.deepEqual(effects.paletteAt(0), effects.paletteAt(27));
    for (let time = 0; time <= 54; time += 0.25) {
        const current = effects.paletteAt(time), next = effects.paletteAt(time + 1 / 60);
        current.forEach((channel, i) => {
            assert.ok(channel >= 0 && channel <= 1);
            assert.ok(Math.abs(channel - next[i]) < 0.002);
        });
    }
    const html = fs.readFileSync(path.join(__dirname, '../api/dashboard.html'), 'utf8');
    assert.ok(html.includes('uniforms.uTint.value.set(...tint);'));
    assert.ok(html.includes('holoSatelliteCloud.material.color.setRGB(...tint);'));
    assert.ok(html.includes('vec3 sprite = vec3(tex.a);'));
    assert.ok(html.includes('const rgb = tint.map(channel => Math.round(channel * 255))'));
});

test('skin particles use bounded micro-movement without speeding up the face clock', () => {
    for (const amplitude of Object.values(effects.FACE_DRIFT)) assert.ok(amplitude > 0 && amplitude < 0.2);
    const html = fs.readFileSync(path.join(__dirname, '../api/dashboard.html'), 'utf8');
    assert.ok(html.includes('const driftTime = mw > 0.4 ? effectTime : t;'));
    for (const axis of ['x', 'y', 'z']) assert.ok(html.includes(`mw <= 0.4 ? faceDrift.${axis}`));
    assert.ok(html.includes('float shimmer = 0.96 + 0.04 * sin'));
});

test('face starts absent, assembles rapidly, and hides immediately', () => {
    const state = effects.createFormationState();
    assert.deepEqual(state, {value: 0, target: 0});
    assert.equal(effects.advanceFormation(state, 1), 0);
    assert.equal(effects.toggleFormation(state), 1);
    const midway = effects.advanceFormation(state, effects.FORMATION_SECONDS / 2);
    assert.equal(midway, 0.5);
    assert.equal(effects.advanceFormation(state, effects.FORMATION_SECONDS), 1);
    assert.equal(effects.toggleFormation(state), 0);
    assert.equal(state.value, 0);
    assert.equal(effects.advanceFormation(state, effects.FORMATION_SECONDS), 0);
    assert.ok(effects.FORMATION_SECONDS <= 0.35);
});

test('rapid formation is frame-rate independent and dismissal clears partial assembly', () => {
    function simulate(fps) {
        const state = effects.createFormationState();
        effects.toggleFormation(state);
        for (let i = 0; i < fps / 10; i++) effects.advanceFormation(state, 1 / fps);
        return state;
    }
    const a = simulate(30), b = simulate(120);
    assert.ok(Math.abs(a.value - b.value) < 1e-10);
    const before = a.value;
    effects.toggleFormation(a);
    assert.equal(a.value, 0);
    assert.ok(effects.advanceFormation(a, 1 / 60) < effects.formationBlend(before));
});

test('scatter positions are deterministic and independent of the original face geometry', () => {
    const scatter = effects.createScatter(1000);
    assert.equal(scatter.length, 3000);
    assert.deepEqual(scatter, effects.createScatter(1000));
    for (let i = 0; i < 1000; i++) {
        assert.ok(scatter[i*3] >= -110 && scatter[i*3] <= 110);
        assert.ok(scatter[i*3+1] >= -78 && scatter[i*3+1] <= 88);
        assert.ok(scatter[i*3+2] >= -70 && scatter[i*3+2] <= -12);
    }
    assert.equal(effects.formationBlend(1), 1);
    assert.equal(effects.formationBlend(0), 0);
});

test('assembly waits for the original data and no alternate face or fixed outline is shown', () => {
    const html = fs.readFileSync(path.join(__dirname, '../api/dashboard.html'), 'utf8');
    assert.ok(html.includes('const formation = holoMoleculesGeo ? ZohraFaceEffects.advanceFormation'));
    assert.ok(html.includes("fetch('/static/zohra_reference_molecules.json')"));
    assert.ok(!html.includes('.catch(() => buildProceduralZohraMoleculeFace())'));
    assert.ok(html.includes('holoLines.visible = false;'));
    assert.ok(html.includes('sparkCloud.visible = false;'));
    assert.ok(html.includes('holoCurPos = new Float32Array(holoScatterPos);'));
});

test('detected clap drives full face formation, not a cosmetic effect switch', () => {
    const html = fs.readFileSync(path.join(__dirname, '../api/dashboard.html'), 'utf8');
    const source = html.slice(html.indexOf('function setHoloFormation('),
        html.indexOf('function releaseHoloMicIfUnused()'));
    const formation = effects.createFormationState();
    const button = {textContent: '', setAttribute() {}, classList: {toggle() {}}};
    const bins = spectrum();
    let now = 150;
    const context = vm.createContext({ZohraFaceEffects: effects, holoFormation: formation,
        holoEffectKick: 0, holoEffectMode: 0, holoPreviewMedia: null, holoPlaybackMedia: null,
        holoSoundEnabled: true, holoAudioCtx: {sampleRate}, holoIgnoreMicUntil: 0,
        holoLastSoundSample: 0, holoSoundState: effects.createSoundState(), holoFreqData: bins,
        holoAudioAnalyser: {getByteFrequencyData(data) { data.fill(40, 40, 200); }},
        performance: {now: () => now}, document: {getElementById: () => button},
        setHoloControlStatus() {}, clearVoicePlayback() {}, cancelVoiceResponse() {}, isListening: false});
    vm.runInContext(source, context);
    const clap = new Float32Array(2048);
    clap.fill(0.65, 0, 120);
    assert.equal(context.sampleHoloSound(clap), 'snap-or-clap');
    assert.equal(formation.target, 1);
    assert.equal(button.textContent, 'Hide face');
    assert.equal(context.holoEffectMode, 0);
    now = 300;
    context.sampleHoloSound(new Float32Array(2048));
    now = 1100;
    assert.equal(context.sampleHoloSound(clap), 'snap-or-clap');
    assert.equal(formation.target, 0);
    assert.equal(button.textContent, 'Form face');
    assert.equal(formation.value, 0);
});

test('showing an already formed face keeps its ready status', () => {
    const html = fs.readFileSync(path.join(__dirname, '../api/dashboard.html'), 'utf8');
    const source = html.slice(html.indexOf('function setHoloFormation('), html.indexOf('function toggleHoloFormation('));
    const attributes = {};
    const button = {textContent: '', setAttribute(name, value) { attributes[name] = value; }, classList: {toggle() {}}};
    let status = '';
    const context = vm.createContext({ZohraFaceEffects: effects, holoFormation: {value:1,target:1},
        holoEffectKick:0, document:{getElementById:()=>button}, setHoloControlStatus(message) {status = message;}});
    vm.runInContext(source, context);
    context.setHoloFormation(true);
    assert.equal(status, 'Zohra ready');
    assert.equal(attributes['aria-label'], 'Talk with Zohra');
});

test('explicit English and Hindi dismissal commands cannot match ordinary conversation', () => {
    for (const phrase of ['over', 'OVER!', '\u0913\u0935\u0930', 'now you can go', 'Okay, now you can go.', 'ok over']) {
        assert.equal(effects.portraitCommand(phrase), 'hide');
    }
    for (const phrase of ['move over there', 'go over the trades', 'the market is over', 'go', '', null]) {
        assert.equal(effects.portraitCommand(phrase), null);
    }
});

test('dismissal clears all foreground particles and the background field', () => {
    const html = fs.readFileSync(path.join(__dirname, '../api/dashboard.html'), 'utf8');
    assert.ok(html.includes('active portrait-dormant'));
    assert.ok(html.includes('.portrait-dormant #celestial-particle-canvas,'));
    assert.ok(html.includes('.portrait-dormant #zohra-hologram-canvas { visibility: hidden; }'));
    assert.ok(html.includes('holoGroup.visible = formation > 0;'));
    assert.ok(html.includes('vAlpha = alpha * uFormation;'));
    const source = html.slice(html.indexOf('function setHoloFormation('), html.indexOf('function sampleHoloSound('));
    const state = {value: 1, target: 1};
    const hiddenClasses = new Set();
    let stops = 0;
    const element = {setAttribute() {}, classList: {toggle(name, enabled) {
        if (enabled) hiddenClasses.add(name); else hiddenClasses.delete(name);
    }}};
    const context = vm.createContext({ZohraFaceEffects: effects, holoFormation: state,
        holoPreviewMedia: {onended() { stops++; }}, clearVoicePlayback() { stops++; }, cancelVoiceResponse() {},
        document: {getElementById: () => element}, setHoloControlStatus() {}, isListening: false});
    vm.runInContext(source, context);
    assert.equal(context.handleHoloVoiceCommand('over'), true);
    assert.deepEqual(state, {value: 0, target: 0});
    assert.ok(hiddenClasses.has('portrait-dormant'));
    assert.equal(stops, 2);
    assert.equal(context.handleHoloVoiceCommand('now you can go'), true);
    assert.equal(state.target, 0);
    assert.equal(context.handleHoloVoiceCommand('go over my report'), false);
});

test('faster effects remain separate from facial drift and real-time speech', () => {
    const html = fs.readFileSync(path.join(__dirname, '../api/dashboard.html'), 'utf8');
    assert.equal(effects.MOTION_SPEED, 3);
    assert.ok(html.includes('const effectTime = t * ZohraFaceEffects.MOTION_SPEED;'));
    assert.ok(html.includes('uniforms.uTime.value = effectTime;'));
    assert.ok(html.includes('const driftTime = mw > 0.4 ? effectTime : t;'));
    assert.ok(html.includes('vRim = smoothstep(0.4, 0.9, motionWeight);'));
    assert.ok(html.includes('ZohraFaceSpeech.smoothPose(holoSpeechPose, target, delta)'));
    assert.ok(html.includes('holoGroup.rotation.y = Math.sin(t * 0.28) * 0.012;'));
});

test('hiding the portrait turns Talk off while preserving Sound control listening', () => {
    const html = fs.readFileSync(path.join(__dirname, '../api/dashboard.html'), 'utf8');
    const source = html.slice(html.indexOf('function setHoloFormation('), html.indexOf('function toggleHoloFormation('));
    const toggles = [];
    const element = {setAttribute() {}, classList: {toggle() {}}};
    const context = vm.createContext({ZohraFaceEffects: effects, holoFormation: {value:1,target:1},
        holoPreviewMedia: null, clearVoicePlayback() {}, cancelVoiceResponse() {}, isListening: true,
        toggleVoiceCapture: enabled => toggles.push(enabled),
        document: {getElementById: () => element}, setHoloControlStatus() {}});
    vm.runInContext(source, context);
    context.setHoloFormation(false);
    assert.deepEqual(toggles, [false]);
});

test('snap or clap onset switches once, with cooldown', () => {
    const state = effects.createSoundState();
    const bins = spectrum();
    for (let i = 40; i < 200; i++) bins[i] = 40;
    const silence = new Float32Array(2048);
    const impulse = new Float32Array(2048);
    impulse.fill(0.65, 0, 120);
    assert.equal(effects.detectSound(silence, bins, sampleRate, 100, state), null);
    assert.equal(effects.detectSound(impulse, bins, sampleRate, 150, state), 'snap-or-clap');
    assert.equal(effects.detectSound(silence, bins, sampleRate, 180, state), null);
    assert.equal(effects.detectSound(impulse, bins, sampleRate, 250, state), null);
    effects.detectSound(silence, bins, sampleRate, 1050, state);
    assert.equal(effects.detectSound(impulse, bins, sampleRate, 1100, state), 'snap-or-clap');
});

test('sustained narrow whistle switches; normal voice spectrum does not', () => {
    const state = effects.createSoundState();
    const samples = Float32Array.from({length: 2048}, (_, i) =>
        Math.sin(2 * Math.PI * 1600 * i / sampleRate) * 0.08);
    const tone = spectrum();
    tone[68] = 230;
    tone[67] = tone[69] = 12;
    for (let i = 0; i < 5; i++) {
        const result = effects.detectSound(samples, tone, sampleRate, 100 + i * 75, state);
        assert.equal(result, i === 4 ? 'whistle' : null);
    }
    const broad = spectrum();
    broad.fill(50, 6, 135);
    const voiceState = effects.createSoundState();
    for (let i = 0; i < 15; i++) {
        assert.equal(effects.detectSound(samples, broad, sampleRate, 100 + i * 75, voiceState), null);
    }
});

test('hand pinch produces a bounded pointer and pinch strength', () => {
    const hand = Array.from({length: 21}, () => ({x: 0.5, y: 0.5}));
    hand[5] = {x: 0.25, y: 0.5};
    hand[17] = {x: 0.65, y: 0.5};
    hand[8] = {x: 0.75, y: 0.25};
    hand[4] = {x: 0.76, y: 0.26};
    const gesture = effects.handGesture(hand);
    assert.equal(gesture.x, -0.5);
    assert.equal(gesture.y, 0.5);
    assert.ok(gesture.pinch > 0.9);
    assert.equal(effects.handGesture(null), null);
});
