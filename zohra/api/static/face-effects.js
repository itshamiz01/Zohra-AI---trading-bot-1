(function (root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    else root.ZohraFaceEffects = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    'use strict';

    const MODES = ['Gather', 'Resonance', 'Gesture'];
    const MOTION_SPEED = 3;
    const FORMATION_SECONDS = 0.32;
    const FACE_DRIFT = Object.freeze({x: 0.14, y: 0.10, z: 0.16});
    const PALETTE = [[0.48, 0.92, 0.85], [0.91, 0.68, 0.82], [0.94, 0.86, 0.70]];
    const clamp = (value, low = 0, high = 1) => Math.min(high, Math.max(low, value));

    function paletteAt(seconds) {
        const phase = Math.max(0, seconds) / 9;
        const index = Math.floor(phase) % PALETTE.length;
        const blend = formationBlend(phase - Math.floor(phase));
        const a = PALETTE[index], b = PALETTE[(index + 1) % PALETTE.length];
        return a.map((channel, i) => channel + (b[i] - channel) * blend);
    }

    function createFormationState() {
        return {value: 0, target: 0};
    }

    function toggleFormation(state) {
        return setFormation(state, !state.target);
    }

    function setFormation(state, visible) {
        state.target = visible ? 1 : 0;
        if (!visible) state.value = 0;
        return state.target;
    }

    function portraitCommand(text) {
        const normalized = String(text || '').toLowerCase().replace(/[^a-z\u0900-\u097f\s]/g, ' ')
            .trim().replace(/\s+/g, ' ').replace(/^(?:okay|ok|zohra|zohara)\s+/, '');
        return ['over', '\u0913\u0935\u0930', 'now you can go'].includes(normalized) ? 'hide' : null;
    }

    function advanceFormation(state, delta) {
        const step = Math.max(0, delta) / FORMATION_SECONDS;
        state.value = state.target > state.value ? Math.min(state.target, state.value + step) :
            Math.max(state.target, state.value - step);
        return formationBlend(state.value);
    }

    function formationBlend(value) {
        const progress = clamp(value);
        return progress * progress * (3 - 2 * progress);
    }

    function createScatter(count) {
        const positions = new Float32Array(count * 3);
        let seed = 25309;
        const random = () => {
            seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
            return seed / 4294967296;
        };
        // Independent of portrait coordinates, so the dispersed cloud has no face-shaped outline.
        for (let i = 0; i < count; i++) {
            positions[i*3] = (random() - 0.5) * 220;
            positions[i*3+1] = (random() - 0.5) * 166 + 5;
            positions[i*3+2] = -12 - random() * 58;
        }
        return positions;
    }

    function nextMode(mode) {
        return (mode + 1) % MODES.length;
    }

    function createSoundState() {
        return {noise: 0.008, previousRms: 0, whistleMs: 0, lastTime: 0,
            lastTrigger: -Infinity};
    }

    function detectSound(samples, spectrum, sampleRate, now, state) {
        if (!samples?.length || !spectrum?.length) return null;
        let squareSum = 0, peak = 0;
        for (let i = 0; i < samples.length; i++) {
            const amplitude = Math.abs(samples[i]);
            squareSum += amplitude * amplitude;
            if (amplitude > peak) peak = amplitude;
        }
        const rms = Math.sqrt(squareSum / samples.length);
        const binHz = sampleRate / (spectrum.length * 2);
        let low = 0, high = 0, toneSum = 0, tonePeak = 0, toneHz = 0;
        for (let i = 1; i < spectrum.length; i++) {
            const hz = i * binHz;
            const energy = spectrum[i];
            if (hz >= 120 && hz < 850) low += energy;
            if (hz >= 850 && hz < 6000) high += energy;
            if (hz >= 900 && hz < 3500) {
                toneSum += energy;
                if (energy > tonePeak) { tonePeak = energy; toneHz = hz; }
            }
        }
        const interval = state.lastTime ? clamp(now - state.lastTime, 0, 120) : 0;
        state.lastTime = now;
        const transient = rms > 0.045 && rms > state.noise * 4.5 &&
            rms > Math.max(0.012, state.previousRms) * 2.5 &&
            peak / rms > 2.4 && high > low * 0.45;
        const whistle = rms > 0.012 && rms < 0.3 && toneHz > 0 &&
            tonePeak / Math.max(1, toneSum) > 0.13 && high > low * 1.3;
        state.whistleMs = whistle ? state.whistleMs + interval : 0;
        if (rms < 0.035) state.noise = state.noise * 0.96 + Math.max(0.003, rms) * 0.04;
        state.previousRms = rms;
        if (now - state.lastTrigger < 850) return null;
        if (transient || state.whistleMs >= 260) {
            state.lastTrigger = now;
            state.whistleMs = 0;
            return transient ? 'snap-or-clap' : 'whistle';
        }
        return null;
    }

    function handGesture(landmarks) {
        if (!landmarks || landmarks.length < 18) return null;
        const tip = landmarks[8], thumb = landmarks[4];
        const palm = Math.hypot(landmarks[5].x - landmarks[17].x,
            landmarks[5].y - landmarks[17].y) || 0.1;
        const pinch = Math.hypot(tip.x - thumb.x, tip.y - thumb.y) / palm;
        return {x: clamp(1 - tip.x * 2, -1, 1), y: clamp(1 - tip.y * 2, -1, 1),
            pinch: clamp(1 - pinch / 0.75)};
    }

    return {MODES, MOTION_SPEED, FORMATION_SECONDS, FACE_DRIFT, paletteAt, createFormationState, toggleFormation, setFormation, portraitCommand,
        advanceFormation, formationBlend, createScatter, nextMode, createSoundState, detectSound, handGesture};
});
