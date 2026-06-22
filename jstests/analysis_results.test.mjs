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
