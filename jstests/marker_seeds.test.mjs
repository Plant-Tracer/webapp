import { frameMarkerSeeds } from '../src/app/static/marker_seeds.mjs';

const point = (label, x, frame = 0) => ({label, x, y: 20.8, frame_number: frame, color: '#ff0000'});

test('stepping and direct seeking carry the latest positions without materializing frames', () => {
    const frames = [{markers: [point('Apex', 10.7)]}, {}, {}, {markers: []}];
    const original = JSON.stringify(frames);
    for (const frame of [1, 2, 3, 1]) {
        expect(frameMarkerSeeds(frames, frame)).toEqual([point('Apex', 10.7, frame)]);
    }
    const seeds = frameMarkerSeeds(frames, 3);
    seeds[0].x = 99;
    expect(JSON.stringify(frames)).toBe(original);
});

test('a later explicit edit becomes the seed without overwriting earlier annotations', () => {
    const frames = [{markers: [point('Apex', 10)]}, {}, {markers: [point('Apex', 30, 2)]}, {}];
    expect(frameMarkerSeeds(frames, 3)).toEqual([point('Apex', 30, 3)]);
    expect(frameMarkerSeeds(frames, 1)).toEqual([point('Apex', 10, 1)]);
    expect(frameMarkerSeeds(frames, 2)).toEqual([point('Apex', 30, 2)]);
});

test('traced gaps and a marker lost from an existing annotation remain missing', () => {
    const frames = [{markers: [point('Apex', 10), point('Ruler 0mm', 5)]}, {},
        {markers: [point('Ruler 0mm', 5, 2)]}, {}];
    expect(frameMarkerSeeds(frames, 1, 2)).toEqual([]);
    expect(frameMarkerSeeds(frames, 3, 2)).toEqual([point('Ruler 0mm', 5, 3)]);
    frames[2].markers = [];
    expect(frameMarkerSeeds(frames, 3, 2)).toEqual([]);
});

test('deleting a marker from saved data cannot resurrect it during a seek', () => {
    const frames = [{markers: [point('Apex', 10), point('Ruler 0mm', 5)]}, {}, {}];
    expect(frameMarkerSeeds(frames, 2)).toHaveLength(2);
    frames[0].markers = frames[0].markers.filter(marker => marker.label !== 'Apex');
    expect(frameMarkerSeeds(frames, 2).map(marker => marker.label)).toEqual(['Ruler 0mm']);
    expect(frameMarkerSeeds([], 0)).toEqual([]);
    expect(frameMarkerSeeds([{}, {}], 1)).toEqual([]);
});
