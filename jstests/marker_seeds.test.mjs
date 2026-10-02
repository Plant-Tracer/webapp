import { MarkerSeedIndex } from '../src/app/static/marker_seeds.mjs';

const point = (label, x, frame = 0) => ({label, x, y: 20.8, frame_number: frame, color: '#ff0000'});
const carried = (label, x, frame) => ({...point(label, x, frame), is_manual: false, is_traced: false});

test('stepping and direct seeking carry the latest positions without materializing frames', () => {
    const frames = [{markers: [point('Apex', 10.7)]}, {}, {}, {markers: []}];
    const original = JSON.stringify(frames);
    const index = new MarkerSeedIndex(frames);
    for (const frame of [1, 2, 3, 1]) {
        expect(index.forFrame(frame)).toEqual([carried('Apex', 10.7, frame)]);
    }
    const seeds = index.forFrame(3);
    seeds[0].x = 99;
    expect(JSON.stringify(frames)).toBe(original);
});

test('a later explicit edit becomes the seed without overwriting earlier annotations', () => {
    const frames = [{markers: [point('Apex', 10)]}, {}, {}, {}];
    const index = new MarkerSeedIndex(frames);
    expect(index.forFrame(3)).toEqual([carried('Apex', 10, 3)]);
    frames[2].markers = [point('Apex', 30, 2)];
    index.invalidate();
    expect(index.forFrame(3)).toEqual([carried('Apex', 30, 3)]);
    expect(index.forFrame(1)).toEqual([carried('Apex', 10, 1)]);
    expect(index.forFrame(2)).toEqual([point('Apex', 30, 2)]);
    frames[2].markers[0].x = 40;
    expect(index.forFrame(3)).toEqual([carried('Apex', 40, 3)]);
});

test('a movie frontier cannot hide earlier seeds or markers absent from another marker trace', () => {
    const frames = [{markers: [point('Apex', 10), point('Ruler 0mm', 5)]}, {},
        {markers: [point('Ruler 0mm', 6, 2)]}, {}];
    const index = new MarkerSeedIndex(frames);
    expect(index.forFrame(1, 2)).toEqual([carried('Apex', 10, 1), carried('Ruler 0mm', 5, 1)]);
    expect(index.forFrame(3, 2)).toEqual([carried('Apex', 10, 3), carried('Ruler 0mm', 6, 3)]);
    frames[2].markers = [];
    frames[2].marker_seed_boundary = true;
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
    expect(index.forFrame(3)).toEqual([carried('Apex', 10, 3)]);
    frames[1].marker_seed_boundary = true;
    index.invalidate();
    expect(index.forFrame(1)).toEqual([]);
    expect(index.forFrame(3)).toEqual([]);
    frames[2].markers = [point('Apex', 30, 2)];
    index.invalidate();
    expect(index.forFrame(3)).toEqual([carried('Apex', 30, 3)]);
});

test('trim seeds supply editable positions without becoming stored annotations', () => {
    const frames = [{markers: [point('Apex', 10)]},
        {markers: [], trim_seed_markers: [point('Apex', 30, 1)]}, {}];
    const index = new MarkerSeedIndex(frames);
    expect(index.forFrame(1)).toEqual([point('Apex', 30, 1)]);
    expect(index.forFrame(2)).toEqual([carried('Apex', 30, 2)]);
    expect(frames[1].markers).toEqual([]);
    frames[1].markers = [];
    frames[1].marker_seed_boundary = true;
    delete frames[1].trim_seed_markers;
    index.invalidate();
    expect(index.forFrame(2)).toEqual([]);
});

test('deleting the last trim seed cannot revive a marker omitted from that seed', () => {
    const frames = [{markers: [point('Apex', 10), point('Ruler 0mm', 5)]},
        {trim_seed_markers: [point('Apex', 30, 1)]}, {}, {}];
    const index = new MarkerSeedIndex(frames);
    expect(index.forFrame(3)).toEqual([carried('Apex', 30, 3), carried('Ruler 0mm', 5, 3)]);
    frames[0].markers = frames[0].markers.filter(marker => marker.label !== 'Apex');
    frames[1].trim_seed_markers = frames[1].trim_seed_markers.filter(marker => marker.label !== 'Apex');
    index.invalidate();
    expect(index.forFrame(0)).toEqual([point('Ruler 0mm', 5)]);
    expect(index.forFrame(1)).toEqual([]);
    expect(index.forFrame(3)).toEqual([]);
    frames[2].markers = [point('Apex', 30, 2)];
    index.invalidate();
    expect(index.forFrame(3)).toEqual([carried('Apex', 30, 3)]);
});


test('a new leaf is present after its birth alongside existing computed points', () => {
    const frames = Array.from({length: 5}, (_, n) => ({markers: [
        {...point('Apex', 10 + n, n), is_manual: false, is_traced: true}]}));
    frames[2].markers.push({...point('Leaf', 30, 2), is_manual: true, is_traced: false});
    const original = JSON.stringify(frames);
    const index = new MarkerSeedIndex(frames);
    expect(index.forFrame(1).map(p => p.label)).toEqual(['Apex']);
    expect(index.forFrame(4)).toEqual([
        {...point('Apex', 14, 4), is_manual: false, is_traced: true}, carried('Leaf', 30, 4)]);
    expect(JSON.stringify(frames)).toBe(original);
});

test('manual edits propagate across untraced snapshots but preserve later traced positions', () => {
    const frames = [{markers: [{...point('Apex', 10), is_manual: true}]}, {},
        {markers: [carried('Apex', 10, 2), {...point('Leaf', 20, 2), is_manual: true}]}, {},
        {markers: [{...point('Apex', 50, 4), is_manual: false, is_traced: true}]}];
    const index = new MarkerSeedIndex(frames);
    frames[1].markers = [{...point('Apex', 30, 1), is_manual: true}];
    expect(index.forFrame(0)[0].x).toBe(10);
    expect(index.forFrame(2).map(p => [p.label, p.x])).toEqual([['Apex', 30], ['Leaf', 20]]);
    expect(index.forFrame(3)[0].x).toBe(30);
    expect(index.forFrame(4)[0].x).toBe(50);
    expect(new MarkerSeedIndex(JSON.parse(JSON.stringify(frames))).forFrame(3)).toEqual(index.forFrame(3));
});
