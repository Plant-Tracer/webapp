import { MarkerSeedIndex } from '../src/app/static/marker_seeds.mjs';

const point = (label, x, frame = 0) => ({label, x, y: 20.8, frame_number: frame, color: '#ff0000'});

test('stepping and direct seeking carry the latest positions without materializing frames', () => {
    const frames = [{markers: [point('Apex', 10.7)]}, {}, {}, {markers: []}];
    const original = JSON.stringify(frames);
    const index = new MarkerSeedIndex(frames);
    for (const frame of [1, 2, 3, 1]) {
        expect(index.forFrame(frame)).toEqual([point('Apex', 10.7, frame)]);
    }
    const seeds = index.forFrame(3);
    seeds[0].x = 99;
    expect(JSON.stringify(frames)).toBe(original);
});

test('a later explicit edit becomes the seed without overwriting earlier annotations', () => {
    const frames = [{markers: [point('Apex', 10)]}, {}, {}, {}];
    const index = new MarkerSeedIndex(frames);
    expect(index.forFrame(3)).toEqual([point('Apex', 10, 3)]);
    frames[2].markers = [point('Apex', 30, 2)];
    index.invalidate();
    expect(index.forFrame(3)).toEqual([point('Apex', 30, 3)]);
    expect(index.forFrame(1)).toEqual([point('Apex', 10, 1)]);
    expect(index.forFrame(2)).toEqual([point('Apex', 30, 2)]);
    frames[2].markers[0].x = 40;
    expect(index.forFrame(3)).toEqual([point('Apex', 40, 3)]);
});

test('traced gaps and a marker lost from an existing annotation remain missing', () => {
    const frames = [{markers: [point('Apex', 10), point('Ruler 0mm', 5)]}, {},
        {markers: [point('Ruler 0mm', 5, 2)]}, {}];
    const index = new MarkerSeedIndex(frames);
    expect(index.forFrame(1, 2)).toEqual([]);
    expect(index.forFrame(3, 2)).toEqual([point('Ruler 0mm', 5, 3)]);
    frames[2].markers = [];
    index.invalidate();
    expect(index.forFrame(3, 2)).toEqual([]);
});

test('deleting a marker from saved data cannot resurrect it during a seek', () => {
    const frames = [{markers: [point('Apex', 10), point('Ruler 0mm', 5)]}, {}, {}];
    const index = new MarkerSeedIndex(frames);
    expect(index.forFrame(2)).toHaveLength(2);
    frames[0].markers = frames[0].markers.filter(marker => marker.label !== 'Apex');
    index.invalidate();
    expect(index.forFrame(2).map(marker => marker.label)).toEqual(['Ruler 0mm']);
    expect(new MarkerSeedIndex([]).forFrame(0)).toEqual([]);
    expect(new MarkerSeedIndex([{}, {}]).forFrame(1)).toEqual([]);
});

test('sequential navigation reads annotations a linear number of times', () => {
    let reads = 0;
    const frames = Array.from({length: 50000}, (_, frame) => {
        const markers = frame === 0 ? [point('Apex', 10)] : [];
        return {get markers() { reads++; return markers; }};
    });
    const index = new MarkerSeedIndex(frames);
    for (let frame = 0; frame < frames.length; frame++) {
        expect(index.forFrame(frame)[0].frame_number).toBe(frame);
    }
    expect(reads).toBeLessThanOrEqual(4 * frames.length);
});

test('explicit empty annotations stop carrying until a later annotation supplies new seeds', () => {
    const frames = [{markers: [point('Apex', 10)]}, {markers: []}, {}, {}];
    const index = new MarkerSeedIndex(frames);
    expect(index.forFrame(3)).toEqual([point('Apex', 10, 3)]);
    frames[1].marker_seed_boundary = true;
    index.invalidate();
    expect(index.forFrame(1)).toEqual([]);
    expect(index.forFrame(3)).toEqual([]);
    frames[2].markers = [point('Apex', 30, 2)];
    index.invalidate();
    expect(index.forFrame(3)).toEqual([point('Apex', 30, 3)]);
});
