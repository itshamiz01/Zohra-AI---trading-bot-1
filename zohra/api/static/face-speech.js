(function (root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    else root.ZohraFaceSpeech = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    'use strict';
    const SCALE = 178 / 458;
    const ARTICULATION = Object.freeze({maxOpen: 0.72, vertical: 2.6, horizontal: 1.05,
        depth: 0.24, roundDepth: 0.32, cavityHeight: 1.3, cavityDrop: 0.9});
    const clamp = (value, min = 0, max = 1) => Math.min(max, Math.max(min, value));
    const smooth = (a, b, value) => {
        const t = clamp((value - a) / (b - a));
        return t * t * (3 - 2 * t);
    };

    function referenceWeights(x, y, motion = 0.22) {
        // Landmarks belong to the 499 x 458 reference, not the older portrait.
        const px = x / (SCALE * 1.03) + 249;
        const py = 232 + (3.5 - y) / SCALE;
        const u = (px - 250) / 39;
        if (Math.abs(u) >= 1 || py < 194 || py >= 262 || motion > 0.4) return [0, 0, 0];
        const across = Math.pow(1 - u * u, 1.7);
        const seam = 216 - 4 * u * u;
        const below = py - seam;
        const vertical = below <= 0
            ? -0.22 * across * smooth(-22, -2, below)
            : across * (1 - smooth(8, 46, below));
        const lip = across * (1 - smooth(7, 17, Math.abs(below)));
        return [vertical, lip, u];
    }

    function createRig(molecules, kind = 'reference') {
        const vertical = new Float32Array(molecules.length);
        const lip = new Float32Array(molecules.length);
        const horizontal = new Float32Array(molecules.length);
        let depth = 0, count = 0;
        molecules.forEach((m, i) => {
            if (kind === 'reference') {
                [vertical[i], lip[i], horizontal[i]] = referenceWeights(m[0], m[1], m[9]);
            } else {
                // The fallback uses its own world-space anatomy and never moves the neck.
                const u = m[0] / 14;
                if (Math.abs(u) < 1 && m[1] > -40 && m[1] < -10 && (m[9] ?? 0) < 0.5) {
                    vertical[i] = m[7] || 0;
                    lip[i] = Math.abs(vertical[i]);
                    horizontal[i] = u;
                }
            }
            if (lip[i] > 0.65) { depth += m[2]; count++; }
        });
        return {vertical, lip, horizontal,
            mouth: {x: kind === 'reference' ? SCALE * 1.03 : 0,
                y: kind === 'reference' ? (232 - 216) * SCALE + 3.5 : -18.5,
                z: count ? depth / count : 18, halfWidth: kind === 'reference' ? 12.2 : 9.5}};
    }

    function measure(samples, frequencies, sampleRate = 48000) {
        if (!samples?.length) return {open: 0, round: 0};
        let energy = 0;
        for (const sample of samples) energy += sample * sample;
        const rms = Math.sqrt(energy / samples.length);
        if (rms < 0.008) return {open: 0, round: 0};
        const open = ARTICULATION.maxOpen * clamp(Math.pow((rms - 0.008) / 0.16, 0.7));
        let low = 0, high = 0;
        if (frequencies?.length) {
            const binHz = sampleRate / (frequencies.length * 2);
            for (let i = 1; i < frequencies.length; i++) {
                const hz = i * binHz;
                if (hz >= 120 && hz < 800) low += frequencies[i];
                if (hz >= 800 && hz < 3200) high += frequencies[i];
            }
        }
        return {open, round: low + high ? clamp((low / (low + high) - 0.25) * 1.5) : 0};
    }

    function smoothPose(current, target, delta) {
        const dt = clamp(delta, 0, 0.1);
        const open = clamp(target.open, 0, ARTICULATION.maxOpen);
        const attack = open > current.open ? 0.05 : 0.07;
        return {open: clamp(current.open + (open - current.open) * (1 - Math.exp(-dt / attack)),
                0, ARTICULATION.maxOpen),
            round: current.round + (clamp(target.round) - current.round) * (1 - Math.exp(-dt / 0.075))};
    }

    function displacement(rig, index, pose) {
        const open = clamp(pose.open, 0, ARTICULATION.maxOpen);
        const round = clamp(pose.round);
        return {
            x: -rig.horizontal[index] * rig.lip[index] * round * open * ARTICULATION.horizontal,
            y: -rig.vertical[index] * open * ARTICULATION.vertical,
            z: rig.lip[index] * open * (ARTICULATION.depth + round * ARTICULATION.roundDepth)
        };
    }

    // Web Speech exposes word boundaries, not an audio stream. Only that preview
    // uses these estimated vowel/closed-lip cues; server speech uses measured audio.
    function previewPose(text, elapsed, offset = 0) {
        const index = Math.max(0, offset + Math.floor(elapsed / 0.085));
        const letter = text.toLowerCase()[index] || ' ';
        if (/[\s.,!?bmp]/.test(letter)) return {open: 0, round: 0};
        if (/[ou]/.test(letter)) return {open: 0.40, round: 0.8};
        if (/[ae]/.test(letter)) return {open: 0.48, round: 0.05};
        if (/[iy]/.test(letter)) return {open: 0.28, round: 0.05};
        return {open: 0.16, round: 0.15};
    }

    return {ARTICULATION, referenceWeights, createRig, measure, smoothPose, displacement, previewPose};
});
