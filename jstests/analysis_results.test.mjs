import {
    gravitropism_results,
    circumnutation_results,
    inflection_angle,
    distance_between,
} from 'analysis_results.mjs';

describe('distance_between', () => {
    test('Euclidean distance (3-4-5)', () => {
        expect(distance_between({ x: 0, y: 0 }, { x: 3, y: 4 })).toBe(5);
    });
});

describe('gravitropism_results - distance', () => {
    test('first->last displacement, pixels', () => {
        const { distance } = gravitropism_results({
            firstTip: { x: 0, y: 0 }, lastTip: { x: 3, y: 4 },
        });
        expect(distance).toBe(5);
    });

    test('scaled to mm', () => {
        const { distance } = gravitropism_results({
            firstTip: { x: 0, y: 0 }, lastTip: { x: 3, y: 4 }, scale: 2,
        });
        expect(distance).toBe(10);
    });

    test('null distance when a tip is missing', () => {
        const { distance, angle } = gravitropism_results({ firstTip: { x: 0, y: 0 } });
        expect(distance).toBeNull();
        expect(angle).toBeNull();
    });
});

describe('gravitropism_results - angle (law of cosines)', () => {
    test('right angle (90 degrees)', () => {
        const { angle } = gravitropism_results({
            firstTip: { x: 0, y: 0 }, lastTip: { x: 2, y: 0 },
            firstInflection: { x: 1, y: 1 }, lastInflection: { x: 1, y: 1 },
        });
        expect(angle).toBeCloseTo(90, 6);
    });

    test('straight line (180 degrees)', () => {
        const { angle } = gravitropism_results({
            firstTip: { x: 0, y: 0 }, lastTip: { x: 2, y: 0 },
            firstInflection: { x: 1, y: 0 }, lastInflection: { x: 1, y: 0 },
        });
        expect(angle).toBeCloseTo(180, 6);
    });

    test('uses per-frame inflection positions (tracked per frame)', () => {
        // Inflection moves between frames but the geometry still yields 180 degrees.
        const { angle } = gravitropism_results({
            firstTip: { x: 0, y: 0 }, lastTip: { x: 2, y: 0 },
            firstInflection: { x: 0, y: 1 }, lastInflection: { x: 2, y: 1 },
        });
        expect(angle).toBeCloseTo(180, 6);
    });

    test('angle is scale-invariant', () => {
        const args = {
            firstTip: { x: 0, y: 0 }, lastTip: { x: 2, y: 0 },
            firstInflection: { x: 1, y: 1 }, lastInflection: { x: 1, y: 1 },
        };
        const a1 = gravitropism_results({ ...args, scale: 1 }).angle;
        const a5 = gravitropism_results({ ...args, scale: 5 }).angle;
        expect(a5).toBeCloseTo(a1, 9);
    });

    test('null angle when no inflection point present', () => {
        const { angle } = gravitropism_results({
            firstTip: { x: 0, y: 0 }, lastTip: { x: 2, y: 0 },
        });
        expect(angle).toBeNull();
    });

    test('null angle when a tip coincides with the inflection point (degenerate)', () => {
        const angle = inflection_angle(
            { x: 1, y: 1 }, { x: 2, y: 0 }, { x: 1, y: 1 }, { x: 1, y: 1 });
        expect(angle).toBeNull();
    });
});

describe('circumnutation_results - max amplitude', () => {
    test('horizontal x-range over all frames, pixels', () => {
        const { maxAmplitude } = circumnutation_results({
            tipPoints: [{ x: 5, y: 0 }, { x: 1, y: 9 }, { x: 9, y: 2 }, { x: 3, y: 4 }],
        });
        expect(maxAmplitude).toBe(8);
    });

    test('scaled to mm', () => {
        const { maxAmplitude } = circumnutation_results({
            tipPoints: [{ x: 1, y: 0 }, { x: 9, y: 0 }], scale: 2,
        });
        expect(maxAmplitude).toBe(16);
    });

    test('null when there are no points', () => {
        expect(circumnutation_results({ tipPoints: [] }).maxAmplitude).toBeNull();
    });
});

describe('gravitropism_results - rate', () => {
    const base = { firstTip: { x: 0, y: 0 }, lastTip: { x: 3, y: 4 } }; // distance 5

    test('per-minute rate uses frames / fpm', () => {
        const { rate, rateTimeUnit } = gravitropism_results({
            ...base, firstFrameNumber: 0, lastFrameNumber: 10, fpm: 5,
        });
        // elapsed = 10 frames / 5 fpm = 2 min; rate = 5 / 2
        expect(rate).toBeCloseTo(2.5, 6);
        expect(rateTimeUnit).toBe('min');
    });

    test('per-frame rate when fpm is null', () => {
        const { rate, rateTimeUnit } = gravitropism_results({
            ...base, firstFrameNumber: 0, lastFrameNumber: 10, fpm: null,
        });
        expect(rate).toBeCloseTo(0.5, 6);
        expect(rateTimeUnit).toBe('frame');
    });

    test('rate is null when the frame span is zero', () => {
        const { rate } = gravitropism_results({
            ...base, firstFrameNumber: 4, lastFrameNumber: 4, fpm: 5,
        });
        expect(rate).toBeNull();
    });

    test('rate is null when frame numbers are absent', () => {
        expect(gravitropism_results({ ...base }).rate).toBeNull();
    });
});

describe('circumnutation_results - rate', () => {
    test('rate uses time between the x-extreme frames', () => {
        const { maxAmplitude, rate, rateTimeUnit } = circumnutation_results({
            tipPoints: [
                { x: 5, y: 0, frame_number: 0 },
                { x: 1, y: 0, frame_number: 2 },  // min x at frame 2
                { x: 9, y: 0, frame_number: 8 },  // max x at frame 8
            ],
            fpm: null,
        });
        expect(maxAmplitude).toBe(8);
        // elapsed = |8 - 2| = 6 frames; rate = 8 / 6
        expect(rate).toBeCloseTo(8 / 6, 6);
        expect(rateTimeUnit).toBe('frame');
    });

    test('per-minute rate divides the extreme span by fpm', () => {
        const { rate, rateTimeUnit } = circumnutation_results({
            tipPoints: [
                { x: 1, y: 0, frame_number: 0 },
                { x: 9, y: 0, frame_number: 4 },
            ],
            fpm: 2,
        });
        // elapsed = 4 frames / 2 fpm = 2 min; rate = 8 / 2
        expect(rate).toBeCloseTo(4, 6);
        expect(rateTimeUnit).toBe('min');
    });

    test('rate is null when the x extremes fall on the same frame', () => {
        const { rate } = circumnutation_results({
            tipPoints: [
                { x: 1, y: 0, frame_number: 3 },
                { x: 9, y: 0, frame_number: 3 },
            ],
            fpm: null,
        });
        expect(rate).toBeNull();
    });
});
