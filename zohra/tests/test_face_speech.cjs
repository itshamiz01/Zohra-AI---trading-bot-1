const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const speech = require('../api/static/face-speech.js');
const data = JSON.parse(fs.readFileSync(path.join(__dirname, '../api/static/zohra_reference_molecules.json'), 'utf8'));
const rig = speech.createRig(data.molecules);
const scale = 178 / 458;
const xy = (px, py) => [(px - 249) * scale * 1.03, (232 - py) * scale + 3.5];

test('actual upper and lower lips move in opposite directions', () => {
    const upper = speech.referenceWeights(...xy(250, 209));
    const lower = speech.referenceWeights(...xy(250, 224));
    assert.ok(upper[0] < -0.15);
    assert.ok(lower[0] > 0.95);
    assert.equal(speech.referenceWeights(...xy(250, 280))[0], 0);
    assert.equal(speech.referenceWeights(...xy(250, 190))[0], 0);
    assert.equal(speech.referenceWeights(...xy(250, 216), 1.18)[0], 0);
});

test('real portrait has lip movement, no speech displacement on neck or eyes', () => {
    let upper = 0, lower = 0, neck = 0;
    data.molecules.forEach((m, i) => {
        const py = 232 + (3.5 - m[1]) / scale;
        const movement = speech.displacement(rig, i, {open: 1, round: 0.7});
        if (py >= 262 || py < 194) {
            assert.equal(movement.y || 0, 0);
            assert.equal(movement.z || 0, 0);
            assert.equal(movement.x || 0, 0);
            neck++;
        }
        if (py >= 204 && py <= 216 && movement.y > 0.2) upper++;
        if (py > 216 && py <= 228 && movement.y < -0.9) lower++;
    });
    assert.ok(upper > 100 && lower > 100 && neck > 1000, `${upper} upper, ${lower} lower, ${neck} unaffected`);
});

test('rest pose exactly preserves portrait and active poses remain bounded', () => {
    data.molecules.forEach((m, i) => {
        for (const v of Object.values(speech.displacement(rig, i, {open: 0, round: 0}))) assert.equal(v || 0, 0);
        const move = speech.displacement(rig, i, {open: 1, round: 1});
        assert.ok(move.y >= -1.8721 && move.y <= 0.413);
        assert.ok(Math.abs(move.x) <= 0.7561 && move.z <= 0.404);
    });
});

test('outgoing waveform opens lips; silence and quiet background close them', () => {
    assert.equal(speech.measure(new Float32Array(1024)).open, 0);
    assert.equal(speech.measure(new Float32Array(1024).fill(0.003)).open, 0);
    const samples = Float32Array.from({length: 1024}, (_, i) => Math.sin(i * 0.1) * 0.2);
    const pose = speech.measure(samples);
    assert.ok(pose.open > 0.45 && pose.open <= speech.ARTICULATION.maxOpen);
});

test('loud playback cannot create an exaggerated opening or cavity', () => {
    const pose = speech.measure(new Float32Array(2048).fill(1));
    assert.equal(pose.open, speech.ARTICULATION.maxOpen);
    const smoothed = speech.smoothPose({open: 0.5, round: 0}, {open: 10, round: 10}, 0.1);
    assert.ok(smoothed.open <= 0.72 && smoothed.round <= 1);
    assert.ok(pose.open * speech.ARTICULATION.cavityHeight < 1);
    const html = fs.readFileSync(path.join(__dirname, '../api/dashboard.html'), 'utf8');
    assert.ok(html.includes('const articulation = ZohraFaceSpeech.ARTICULATION;'));
    assert.ok(html.includes('const spkY = -sw * mo * articulation.vertical;'));
    assert.ok(html.includes('mo * articulation.cavityHeight'));
});

test('release closes lips and smoothing does not depend on frame rate', () => {
    function simulate(fps) {
        let pose = {open: 0, round: 0};
        for (let i = 0; i < fps / 2; i++) pose = speech.smoothPose(pose, {open: 0.8, round: 0.5}, 1 / fps);
        return pose;
    }
    assert.ok(Math.abs(simulate(30).open - simulate(120).open) < 0.0001);
    let pose = simulate(60);
    for (let i = 0; i < 30; i++) pose = speech.smoothPose(pose, {open: 0, round: 0}, 1 / 60);
    assert.ok(pose.open < 0.001);
});

test('preview cue closes bilabial consonants and rounds vowels', () => {
    assert.equal(speech.previewPose('m', 0).open, 0);
    assert.equal(speech.previewPose('p', 0).open, 0);
    assert.ok(speech.previewPose('o', 0).round > 0.5);
    assert.equal(speech.previewPose('a', 1).open, 0);
});

function playbackHarness(connect) {
    const played = [], disconnected = [], revoked = [];
    class Audio {
        constructor(src) { this.src = src; this.paused = true; }
        async play() { this.paused = false; played.push(this); }
        pause() { this.paused = true; }
    }
    const context = vm.createContext({Audio, console, setTimeout,
        URL: {revokeObjectURL: url => revoked.push(url)},
        document: {addEventListener() {}, getElementById() { return null; }},
        connectHologramPlayback: connect || (async () => {}),
        disconnectHologramPlayback: media => disconnected.push(media)
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../api/static/workspaces.js'), 'utf8') + `
        globalThis.controls = {queue: voiceQueue, play: playVoiceQueue, stop: clearVoicePlayback};`, context);
    return {...context.controls, played, disconnected, revoked};
}

test('voice chunks use output analysis, play sequentially, and detach on interruption', async () => {
    const attached = [];
    const harness = playbackHarness(async media => attached.push(media));
    harness.queue.push('blob:first', 'blob:second');
    await harness.play();
    assert.equal(harness.played.length, 1);
    assert.equal(attached[0], harness.played[0]);
    harness.played[0].onended();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(harness.played.length, 2);
    assert.equal(harness.played[1].src, 'blob:second');
    harness.stop();
    assert.equal(harness.played[1].paused, true);
    assert.equal(harness.disconnected.length, 2);
    assert.equal(harness.queue.length, 0);
});

test('stopping during audio-context startup cannot start stale playback', async () => {
    let resume;
    const harness = playbackHarness(() => new Promise(resolve => { resume = resolve; }));
    harness.queue.push('blob:cancelled');
    const starting = harness.play();
    harness.stop();
    resume();
    await starting;
    assert.equal(harness.played.length, 0);
});

test('dashboard samples playback, never microphone, for mouth articulation', () => {
    const html = fs.readFileSync(path.join(__dirname, '../api/dashboard.html'), 'utf8');
    const loop = html.slice(html.indexOf('const clock = new THREE.Clock();'), html.indexOf('function toggleTalkingDemo'));
    assert.ok(loop.includes('holoPlaybackAnalyser.getFloatTimeDomainData'));
    assert.ok(!loop.includes('holoAudioAnalyser.getByteFrequencyData'));
    for (const [, source] of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) {
        if (source.trim()) new vm.Script(source);
    }
});
