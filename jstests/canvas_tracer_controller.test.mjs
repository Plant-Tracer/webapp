/* eslint-env jest, node, es6 */
/**
 * @jest-environment jsdom
 */

import { jest } from '@jest/globals';

// canvas_tracer_controller.js is a .js file transpiled by babel to CJS, so its
// "import ... from './foo.mjs'" statements become require() calls.  Jest cannot
// require() a real .mjs file, so we mock all .mjs dependencies up-front with
// jest.unstable_mockModule (ESM mocks) and the .js dependencies with jest.mock
// (CJS mocks).  Both must be registered before the dynamic await-import below.

// ── ESM mocks (.mjs) ────────────────────────────────────────────────────────
jest.unstable_mockModule('canvas_controller.mjs', () => {
    class MockCanvasItem {
        constructor(x, y, name) { this.x = x; this.y = y; this.name = name; }
        contains_point() { return false; }
        loc() { return `(${this.x},${this.y})`; }
    }
    class MockMarker extends MockCanvasItem {
        constructor(x, y, r, fill, stroke, name) {
            super(x, y, name);
            this.r = r; this.fill = fill; this.stroke = stroke;
        }
        contains_point(p) { return Math.hypot(p.x - this.x, p.y - this.y) <= this.r; }
    }
    class MockLine {
        constructor(x, y, x2, y2, width, color) {
            this.x = x; this.y = y; this.x2 = x2; this.y2 = y2;
            this.width = width; this.color = color;
        }
    }
    class MockWebImage {
        constructor(x, y, url) { this.x = x; this.y = y; this.url = url; }
    }
    class MockText {
        constructor(x, y, name, color) { this.x = x; this.y = y; this.name = name; this.color = color; }
    }
    class MockCanvasController {
        constructor() {
            this.objects = [];
            this.selected = null;
            this.zoom = 1;
            this.naturalWidth = 100;
            this.naturalHeight = 100;
            this.did_onload_callback = () => {};
            this.zoom_selector = null;
            this._zoom_storage_key = null;
            // Fake canvas element
            this.c = { style: { cursor: 'auto' }, width: 100, height: 100, addEventListener: () => {} };
        }
        add_object(obj) { this.objects.push(obj); }
        clear_objects() { this.objects = []; }
        clear_selection() { this.selected = null; }
        resize(w, h) { this.naturalWidth = w; this.naturalHeight = h; }
        redraw() {}
        set_zoom() {}
        setup_zoom_storage() {}
    }
    return {
        CanvasController: MockCanvasController,
        CanvasItem: MockCanvasItem,
        Marker: MockMarker,
        Line: MockLine,
        WebImage: MockWebImage,
        Text: MockText,
    };
});

jest.unstable_mockModule('unzipit.module.mjs', () => ({
    unzip: jest.fn().mockResolvedValue({ entries: {} }),
    setOptions: jest.fn(),
}));

// ── CJS mocks (.js) ─────────────────────────────────────────────────────────
// utils.js — provide a chainable $ stub and $.post
const makeEl = () => {
    const el = {
        attr: jest.fn().mockReturnThis(),
        prop: jest.fn().mockReturnThis(),
        off: jest.fn().mockReturnThis(),
        on: jest.fn().mockReturnThis(),
        val: jest.fn().mockReturnValue(''),
        text: jest.fn().mockReturnThis(),
        html: jest.fn().mockReturnThis(),
        hide: jest.fn().mockReturnThis(),
        show: jest.fn().mockReturnThis(),
        css: jest.fn().mockReturnThis(),
        addClass: jest.fn().mockReturnThis(),
        removeClass: jest.fn().mockReturnThis(),
        fadeIn: jest.fn().mockReturnThis(),
    };
    return el;
};
const mockPost = jest.fn().mockReturnValue({
    done: jest.fn().mockReturnThis(),
    fail: jest.fn().mockReturnThis(),
});
const mock$ = jest.fn().mockImplementation(() => makeEl());
mock$.post = mockPost;

jest.unstable_mockModule('utils.js', () => ({ $: mock$ }));

// canvas_movie_controller.js — provide a minimal MovieController base class
jest.unstable_mockModule('canvas_movie_controller.js', () => {
    // Inline the minimal MovieController that TracerController extends.
    // It must set up this.objects, this.div_selector, this.div_controller,
    // this.frame_number, this.frames, and the properties TracerController uses.
    class MockMovieController {
        constructor(div_selector) {
            this.div_selector = div_selector + ' ';
            this.div_controller = div_selector;
            this.objects = [];
            this.frame_number = 0;
            this.frames = [];
            this.playing = 0;
            this.bounce = false;
            this.loop = false;
            this.max_frame_index = 0;
            this.fpm = null;
            this.timer = null;
        }
        add_object(obj) { this.objects.push(obj); }
        clear_objects() { this.objects = []; }
        redraw() {}
        load_movie(frames) { this.frames = frames; }
        goto_frame(f) { this.frame_number = f; }
        set_movie_control_buttons() {}
        enableTrackButtonIfAllowed() {}
        setup_zoom_storage() {}
    }
    return { MovieController: MockMovieController };
});

// ── Required globals ─────────────────────────────────────────────────────────
global.API_BASE = 'http://localhost:8080/';
global.LAMBDA_API_BASE = 'http://localhost:9000/';
global.demo_mode = false;
global.Chart = class { constructor() {} destroy() {} };

// ── Import module under test (after all mocks are registered) ────────────────
const {
    get_ruler_size,
    frame_index_from_zip_name,
    is_movie_tracked,
    create_default_markers,
    calc_scale,
    TracerController,
    trace_movie,
    trace_movie_one_frame,
    trace_movie_frames,
} = await import('canvas_tracer_controller.mjs');

// Also grab the mocked Marker/Line classes for use in tests
const { Marker: MockMarkerClass, Line: MockLineClass } = await import('canvas_controller.mjs');

// Grab MockMovieController so we can spy on its prototype in trace_movie_one_frame tests
const { MovieController: MockMovieControllerClass } = await import('canvas_movie_controller.js');

// Grab the unzip mock so individual tests can configure its return value
const { unzip: mockUnzip } = await import('unzipit.module.mjs');

// ── Helpers ──────────────────────────────────────────────────────────────────
function makeMovieMetadata(overrides = {}) {
    return {
        movie_id: 'test-movie-001',
        rotation: 0,
        last_frame_tracked: -1,
        total_frames: 0,
        width: 200,
        height: 150,
        ...overrides,
    };
}

// ── get_ruler_size ───────────────────────────────────────────────────────────
describe('get_ruler_size', () => {
    test('"Ruler 0mm" → 0', () => {
        expect(get_ruler_size('Ruler 0mm')).toBe(0);
    });

    test('"Ruler 10mm" → 10', () => {
        expect(get_ruler_size('Ruler 10mm')).toBe(10);
    });

    test('"Ruler 100mm" → 100', () => {
        expect(get_ruler_size('Ruler 100mm')).toBe(100);
    });

    test('"Apex" → null', () => {
        expect(get_ruler_size('Apex')).toBeNull();
    });

    test('empty string → null', () => {
        expect(get_ruler_size('')).toBeNull();
    });

    test('"Ruler" alone → null', () => {
        expect(get_ruler_size('Ruler')).toBeNull();
    });

    test('"Ruler 10px" → null (wrong suffix)', () => {
        expect(get_ruler_size('Ruler 10px')).toBeNull();
    });

    test('"Ruler10mm" (no space) → 10', () => {
        expect(get_ruler_size('Ruler10mm')).toBe(10);
    });
});

// ── frame_index_from_zip_name ────────────────────────────────────────────────
describe('frame_index_from_zip_name', () => {
    test('"frame_0000.jpg" → 0', () => {
        expect(frame_index_from_zip_name('frame_0000.jpg')).toBe(0);
    });

    test('"frame_0042.jpg" → 42', () => {
        expect(frame_index_from_zip_name('frame_0042.jpg')).toBe(42);
    });

    test('"frame_9999.jpeg" → 9999', () => {
        expect(frame_index_from_zip_name('frame_9999.jpeg')).toBe(9999);
    });

    test('"path/to/frame_0007.jpg" → 7', () => {
        expect(frame_index_from_zip_name('path/to/frame_0007.jpg')).toBe(7);
    });

    test('unrecognised name → 0 (fallback)', () => {
        expect(frame_index_from_zip_name('image.png')).toBe(0);
    });
});

// ── is_movie_tracked ─────────────────────────────────────────────────────────
describe('is_movie_tracked', () => {
    test('null → false', () => {
        expect(is_movie_tracked(null)).toBe(false);
    });

    test('undefined → false', () => {
        expect(is_movie_tracked(undefined)).toBe(false);
    });

    test('status "TRACING COMPLETED" → true', () => {
        expect(is_movie_tracked({ status: 'TRACING COMPLETED' })).toBe(true);
    });

    test('last_frame_tracked >= 1 with total_frames > 1 → true', () => {
        expect(is_movie_tracked({ last_frame_tracked: 5, total_frames: 10 })).toBe(true);
    });

    test('last_frame_tracked 0 → false', () => {
        expect(is_movie_tracked({ last_frame_tracked: 0, total_frames: 10 })).toBe(false);
    });

    test('total_frames 1 → false (single-frame)', () => {
        expect(is_movie_tracked({ last_frame_tracked: 1, total_frames: 1 })).toBe(false);
    });

    test('missing last_frame_tracked → false', () => {
        expect(is_movie_tracked({ total_frames: 10 })).toBe(false);
    });
});

// ── create_default_markers ───────────────────────────────────────────────────
describe('create_default_markers', () => {
    test('returns array of 3 markers', () => {
        expect(create_default_markers()).toHaveLength(3);
    });

    test('first marker label is "Apex"', () => {
        expect(create_default_markers()[0].label).toBe('Apex');
    });

    test('returns a fresh copy each call', () => {
        const a = create_default_markers();
        const b = create_default_markers();
        expect(a).not.toBe(b);
        a[0].x = 999;
        expect(b[0].x).not.toBe(999);
    });

    test('each marker has numeric x, y and string label', () => {
        for (const m of create_default_markers()) {
            expect(typeof m.x).toBe('number');
            expect(typeof m.y).toBe('number');
            expect(typeof m.label).toBe('string');
        }
    });
});

// ── calc_scale (module-level, uses marker.label) ─────────────────────────────
describe('calc_scale', () => {
    test('no ruler markers → scale 1, pixels', () => {
        const r = calc_scale([{ label: 'Apex', x: 50, y: 50 }]);
        expect(r.scale).toBe(1);
        expect(r.pos_units).toBe('pixels');
    });

    test('one ruler marker → scale 1, pixels (need ≥ 2)', () => {
        const r = calc_scale([{ label: 'Ruler 0mm', x: 0, y: 0 }]);
        expect(r.scale).toBe(1);
        expect(r.pos_units).toBe('pixels');
    });

    test('two horizontal ruler markers → correct scale', () => {
        // Ruler 0mm at x=0, Ruler 10mm at x=100 → 10/100 = 0.1 mm/px
        const r = calc_scale([
            { label: 'Ruler 0mm',  x: 0,   y: 0 },
            { label: 'Ruler 10mm', x: 100, y: 0 },
        ]);
        expect(r.pos_units).toBe('mm');
        expect(r.scale).toBeCloseTo(0.1);
    });

    test('diagonal ruler uses Euclidean distance', () => {
        // 3-4-5 right triangle: pixel distance 50, real distance 10 → 0.2
        const r = calc_scale([
            { label: 'Ruler 0mm',  x: 0,  y: 0 },
            { label: 'Ruler 10mm', x: 30, y: 40 },
        ]);
        expect(r.pos_units).toBe('mm');
        expect(r.scale).toBeCloseTo(0.2);
    });

    test('empty array → scale 1, pixels', () => {
        const r = calc_scale([]);
        expect(r.scale).toBe(1);
        expect(r.pos_units).toBe('pixels');
    });
});

// ── TracerController constructor ─────────────────────────────────────────────
describe('TracerController constructor', () => {
    test('creates an instance with expected properties', () => {
        const tc = new TracerController('div#tc', makeMovieMetadata(), 'my-key');
        expect(tc.movie_id).toBe('test-movie-001');
        expect(tc.api_key).toBe('my-key');
        expect(tc.tracking).toBe(false);
    });

    test('movie_rotation defaults to 0 when null', () => {
        const tc = new TracerController('div#tc', makeMovieMetadata({ rotation: null }), 'k');
        expect(tc.movie_rotation).toBe(0);
    });

    test('last_tracked_frame is -1 when not provided', () => {
        const tc = new TracerController('div#tc', makeMovieMetadata({ last_frame_tracked: undefined }), 'k');
        expect(tc.last_tracked_frame).toBe(-1);
    });

    test('total_frames is 0 when not provided', () => {
        const tc = new TracerController('div#tc', makeMovieMetadata({ total_frames: undefined }), 'k');
        expect(tc.total_frames).toBe(0);
    });

    test('total_frames and last_tracked_frame set from metadata', () => {
        const tc = new TracerController('div#tc', makeMovieMetadata({ total_frames: 42, last_frame_tracked: 41 }), 'k');
        expect(tc.total_frames).toBe(42);
        expect(tc.last_tracked_frame).toBe(41);
    });
});

// ── TracerController.getMaxViewableFrame ─────────────────────────────────────
describe('TracerController.getMaxViewableFrame', () => {
    test('returns 0 when no frames loaded', () => {
        const tc = new TracerController('div#tc', makeMovieMetadata(), 'k');
        expect(tc.getMaxViewableFrame()).toBe(0);
    });

    test('returns 0 when last_tracked_frame is -1', () => {
        const tc = new TracerController('div#tc', makeMovieMetadata({ last_frame_tracked: -1, total_frames: 5 }), 'k');
        tc.frames = new Array(5).fill({});
        expect(tc.getMaxViewableFrame()).toBe(0);
    });

    test('returns last_tracked_frame when within loaded frames', () => {
        const tc = new TracerController('div#tc', makeMovieMetadata({ last_frame_tracked: 3, total_frames: 5 }), 'k');
        tc.frames = new Array(5).fill({});
        expect(tc.getMaxViewableFrame()).toBe(3);
    });

    test('clamps to frames.length - 1 when last_tracked_frame exceeds loaded frames', () => {
        const tc = new TracerController('div#tc', makeMovieMetadata({ last_frame_tracked: 10, total_frames: 20 }), 'k');
        tc.frames = new Array(5).fill({});
        expect(tc.getMaxViewableFrame()).toBe(4);
    });
});

// ── TracerController.calculate_scale (class method, uses marker.name) ────────
describe('TracerController.calculate_scale', () => {
    let tc;
    beforeEach(() => {
        tc = new TracerController('div#tc', makeMovieMetadata(), 'k');
    });

    test('no ruler markers → scale 1, pixels', () => {
        const r = tc.calculate_scale([{ name: 'Apex', x: 50, y: 50 }]);
        expect(r.scale).toBe(1);
        expect(r.pos_units).toBe('pixels');
    });

    test('two ruler markers → mm units with correct scale', () => {
        const r = tc.calculate_scale([
            { name: 'Ruler 0mm',  x: 0,   y: 0 },
            { name: 'Ruler 10mm', x: 100, y: 0 },
        ]);
        expect(r.pos_units).toBe('mm');
        expect(r.scale).toBeCloseTo(0.1);
    });

    test('empty array → scale 1, pixels', () => {
        const r = tc.calculate_scale([]);
        expect(r.scale).toBe(1);
        expect(r.pos_units).toBe('pixels');
    });
});

// ── TracerController.get_markers ─────────────────────────────────────────────
describe('TracerController.get_markers', () => {
    test('returns empty array when no markers', () => {
        const tc = new TracerController('div#tc', makeMovieMetadata(), 'k');
        expect(tc.get_markers()).toEqual([]);
    });

    test('extracts x, y, label from each Marker in objects', () => {
        const tc = new TracerController('div#tc', makeMovieMetadata(), 'k');
        tc.objects.push(new MockMarkerClass(10, 20, 5, 'red', 'red', 'Apex'));
        const markers = tc.get_markers();
        expect(markers).toHaveLength(1);
        expect(markers[0]).toMatchObject({ x: 10, y: 20, label: 'Apex' });
    });

    test('ignores non-Marker objects', () => {
        const tc = new TracerController('div#tc', makeMovieMetadata(), 'k');
        tc.objects.push(new MockLineClass(0, 0, 50, 50, 2, 'blue'));
        tc.objects.push(new MockMarkerClass(10, 20, 5, 'red', 'red', 'Apex'));
        expect(tc.get_markers()).toHaveLength(1);
    });
});

// ── trace_movie_one_frame ─────────────────────────────────────────────────────
describe('trace_movie_one_frame', () => {
    let capturedTc;
    let loadMovieSpy;

    beforeEach(() => {
        jest.clearAllMocks();
        capturedTc = null;
        // Spy on load_movie to capture the TracerController instance created inside
        // trace_movie_one_frame (it is stored in the module-level `cc` variable and
        // not exported, so this is the only way to reach it).
        loadMovieSpy = jest.spyOn(MockMovieControllerClass.prototype, 'load_movie')
            .mockImplementation(function(frames) {
                capturedTc = this;
                this.frames = frames;
            });
    });

    afterEach(() => {
        loadMovieSpy.mockRestore();
        global.demo_mode = false;
    });

    // Convenience wrapper so every test uses the same URL / api_key.
    function callTmof(metadata_frames, metaOverrides = {}) {
        trace_movie_one_frame(
            'movie-id-123',
            'div#tracer',
            makeMovieMetadata(metaOverrides),
            'http://example.com/frame0.jpg',
            metadata_frames,
            'test-api-key'
        );
        return capturedTc;
    }

    // A. Marker selection ─────────────────────────────────────────────────────
    test('uses metadata_frames[0].markers when present and non-empty', () => {
        const markers = [{ x: 10, y: 20, label: 'Apex' }];
        const tc = callTmof({ 0: { markers } });
        expect(tc.frames[0].markers).toEqual(markers);
    });

    test('falls back to create_default_markers() when metadata_frames is null', () => {
        const tc = callTmof(null);
        expect(tc.frames[0].markers).toEqual(create_default_markers());
    });

    test('falls back to create_default_markers() when metadata_frames[0].markers is empty', () => {
        const tc = callTmof({ 0: { markers: [] } });
        expect(tc.frames[0].markers).toEqual(create_default_markers());
    });

    test('falls back to create_default_markers() when metadata_frames has no key 0', () => {
        const tc = callTmof({});
        expect(tc.frames[0].markers).toEqual(create_default_markers());
    });

    // B. Frame structure ──────────────────────────────────────────────────────
    test('load_movie is called with exactly one frame', () => {
        const tc = callTmof(null);
        expect(tc.frames).toHaveLength(1);
    });

    test('frame_url is the supplied frame0_url', () => {
        const tc = callTmof(null);
        expect(tc.frames[0].frame_url).toBe('http://example.com/frame0.jpg');
    });

    // C. Track button and table ───────────────────────────────────────────────
    test('track button is disabled after call', () => {
        const tc = callTmof(null);
        expect(tc.track_button.prop).toHaveBeenCalledWith('disabled', true);
    });

    test('create_marker_table is called once', () => {
        const tableSpy = jest.spyOn(TracerController.prototype, 'create_marker_table');
        callTmof(null);
        expect(tableSpy).toHaveBeenCalledTimes(1);
        tableSpy.mockRestore();
    });

    // D. did_onload_callback — canvas/video resize ────────────────────────────
    // After calling trace_movie_one_frame we clear all mock call histories so
    // that only calls made inside the callback are visible, making assertions precise.

    test('resizes canvas and video when metadata has no dimensions and image has valid natural size', () => {
        const tc = callTmof(null, { width: null, height: null });
        jest.clearAllMocks();
        tc.did_onload_callback({ img: { naturalWidth: 320, naturalHeight: 240 } });
        const canvasIdx = mock$.mock.calls.findIndex(args => args[0] && args[0].includes(' canvas'));
        const videoIdx  = mock$.mock.calls.findIndex(args => args[0] && args[0].includes(' video'));
        expect(canvasIdx).toBeGreaterThanOrEqual(0);
        expect(videoIdx).toBeGreaterThanOrEqual(0);
        expect(mock$.mock.results[canvasIdx].value.attr).toHaveBeenCalledWith('width', 320);
        expect(mock$.mock.results[videoIdx].value.attr).toHaveBeenCalledWith('height', 240);
    });

    test('does not resize canvas when metadata already has dimensions', () => {
        const tc = callTmof(null, { width: 200, height: 150 });
        jest.clearAllMocks();
        tc.did_onload_callback({ img: { naturalWidth: 320, naturalHeight: 240 } });
        const canvasIdx = mock$.mock.calls.findIndex(args => args[0] && args[0].includes(' canvas'));
        expect(canvasIdx).toBe(-1);
    });

    test('does not resize canvas when image natural dimensions are 0', () => {
        const tc = callTmof(null, { width: null, height: null });
        jest.clearAllMocks();
        tc.did_onload_callback({ img: { naturalWidth: 0, naturalHeight: 0 } });
        const canvasIdx = mock$.mock.calls.findIndex(args => args[0] && args[0].includes(' canvas'));
        expect(canvasIdx).toBe(-1);
    });

    // E. did_onload_callback — status message and demo mode ───────────────────
    test('in normal mode: shows ready status and enables track button', () => {
        const tc = callTmof(null);
        jest.clearAllMocks();
        tc.did_onload_callback(null);
        const statusIdx = mock$.mock.calls.findIndex(args => args[0] === '#status-big');
        expect(statusIdx).toBeGreaterThanOrEqual(0);
        expect(mock$.mock.results[statusIdx].value.html)
            .toHaveBeenCalledWith('Movie ready for initial tracing.');
        expect(tc.track_button.prop).toHaveBeenCalledWith('disabled', false);
    });

    test('in demo mode: shows demo message and does not enable track button', () => {
        global.demo_mode = true;
        const tc = callTmof(null);
        jest.clearAllMocks();
        tc.did_onload_callback(null);
        const statusIdx = mock$.mock.calls.findIndex(args => args[0] === '#status-big');
        expect(statusIdx).toBeGreaterThanOrEqual(0);
        expect(mock$.mock.results[statusIdx].value.html)
            .toHaveBeenCalledWith('Movie cannot be traced in demo mode.');
        expect(tc.track_button.prop).not.toHaveBeenCalledWith('disabled', false);
    });
});

// ── trace_movie_frames ────────────────────────────────────────────────────────
describe('trace_movie_frames', () => {
    let capturedTc;
    let loadMovieSpy;
    let setMovieControlButtonsSpy;
    let enableTrackButtonSpy;

    beforeAll(() => {
        // graph_data() calls document.getElementById('apex-xChart/yChart').getContext('2d')
        // jsdom doesn't implement Canvas 2D, so we add minimal stubs.
        ['apex-xChart', 'apex-yChart'].forEach(id => {
            if (!document.getElementById(id)) {
                const el = document.createElement('canvas');
                el.id = id;
                el.getContext = jest.fn().mockReturnValue({});
                document.body.appendChild(el);
            }
        });
        // URL.createObjectURL is not available in jsdom
        global.URL.createObjectURL = jest.fn().mockReturnValue('blob:mock-url');
    });

    beforeEach(() => {
        jest.clearAllMocks();
        capturedTc = null;

        loadMovieSpy = jest.spyOn(MockMovieControllerClass.prototype, 'load_movie')
            .mockImplementation(function (frames) {
                capturedTc = this;
                this.frames = frames;
            });
        setMovieControlButtonsSpy = jest.spyOn(MockMovieControllerClass.prototype, 'set_movie_control_buttons');
        // TracerController overrides enableTrackButtonIfAllowed, so spy on its own prototype
        enableTrackButtonSpy = jest.spyOn(TracerController.prototype, 'enableTrackButtonIfAllowed');
    });

    afterEach(() => {
        loadMovieSpy.mockRestore();
        setMovieControlButtonsSpy.mockRestore();
        enableTrackButtonSpy.mockRestore();
    });

    /** Build a fake unzip `entries` object from a list of filenames. */
    function makeEntries(...names) {
        const entries = {};
        names.forEach(name => {
            entries[name] = { blob: jest.fn().mockResolvedValue({ _name: name }) };
        });
        return entries;
    }

    /** Run trace_movie_frames and return the captured TracerController. */
    async function callTmf(entries, metadata_frames = null, metaOverrides = {}, show_results = true) {
        mockUnzip.mockResolvedValueOnce({ entries });
        await trace_movie_frames(
            'div#tracer',
            makeMovieMetadata(metaOverrides),
            'http://example.com/movie.zip',
            metadata_frames,
            'test-api-key',
            show_results
        );
        return capturedTc;
    }

    // A. Entry filtering ───────────────────────────────────────────────────────
    test('includes only .jpg and .jpeg entries, ignores other types', async () => {
        const tc = await callTmf(makeEntries(
            'frame_0000.jpg', 'frame_0001.jpeg', 'thumb.png', 'notes.txt', 'movie.mp4'
        ));
        expect(tc.frames).toHaveLength(2);
    });

    test('returns zero frames when there are no jpeg entries', async () => {
        const tc = await callTmf(makeEntries('cover.png', 'README.txt'));
        expect(tc.frames).toHaveLength(0);
    });

    // B. Sorting ───────────────────────────────────────────────────────────────
    // Supply entries in reverse order; verify that markers follow sorted frame indices.
    test('sorts frames by frame index regardless of entry order', async () => {
        const entries = makeEntries('frame_0001.jpg', 'frame_0000.jpg');
        const metadata_frames = {
            '0': { markers: [{ x: 1, y: 2, label: 'Apex' }] },
            '1': { markers: [{ x: 9, y: 9, label: 'Base' }] },
        };
        const tc = await callTmf(entries, metadata_frames);
        expect(tc.frames[0].markers[0].label).toBe('Apex');
        expect(tc.frames[1].markers[0].label).toBe('Base');
    });

    // C. Marker selection ──────────────────────────────────────────────────────
    test('uses markers from metadata_frames when present and non-empty', async () => {
        const markers = [{ x: 10, y: 20, label: 'Apex' }];
        const tc = await callTmf(makeEntries('frame_0000.jpg'), { '0': { markers } });
        expect(tc.frames[0].markers).toEqual(markers);
    });

    test('uses [] when metadata_frames is null', async () => {
        const tc = await callTmf(makeEntries('frame_0000.jpg'), null);
        expect(tc.frames[0].markers).toEqual([]);
    });

    test('uses [] when metadata_frames[key].markers is empty', async () => {
        const tc = await callTmf(makeEntries('frame_0000.jpg'), { '0': { markers: [] } });
        expect(tc.frames[0].markers).toEqual([]);
    });

    test('uses [] when frame key is missing from metadata_frames', async () => {
        const tc = await callTmf(makeEntries('frame_0000.jpg'), { '99': { markers: [{ x: 1, y: 2, label: 'Apex' }] } });
        expect(tc.frames[0].markers).toEqual([]);
    });

    // D. Frame URL ─────────────────────────────────────────────────────────────
    test('frame_url is the result of URL.createObjectURL called with the blob', async () => {
        global.URL.createObjectURL.mockReturnValueOnce('blob:test-url-frame0');
        const tc = await callTmf(makeEntries('frame_0000.jpg'));
        expect(tc.frames[0].frame_url).toBe('blob:test-url-frame0');
        expect(global.URL.createObjectURL).toHaveBeenCalledTimes(1);
    });

    test('URL.createObjectURL is called once per jpeg entry', async () => {
        await callTmf(makeEntries('frame_0000.jpg', 'frame_0001.jpg', 'frame_0002.jpg'));
        expect(global.URL.createObjectURL).toHaveBeenCalledTimes(3);
    });

    // E. TracerController setup ────────────────────────────────────────────────
    test('load_movie is called with the correct number of frames', async () => {
        const tc = await callTmf(makeEntries('frame_0000.jpg', 'frame_0001.jpg', 'frame_0002.jpg'));
        expect(tc.frames).toHaveLength(3);
    });

    test('set_movie_control_buttons is called once', async () => {
        await callTmf(makeEntries('frame_0000.jpg'));
        expect(setMovieControlButtonsSpy).toHaveBeenCalledTimes(1);
    });

    test('enableTrackButtonIfAllowed is called once', async () => {
        await callTmf(makeEntries('frame_0000.jpg'));
        expect(enableTrackButtonSpy).toHaveBeenCalledTimes(1);
    });

    // F. show_results ──────────────────────────────────────────────────────────
    test('show_results=true: #analysis-results is shown', async () => {
        await callTmf(makeEntries('frame_0000.jpg'), null, {}, true);
        const idx = mock$.mock.calls.findIndex(args => args[0] === '#analysis-results');
        expect(idx).toBeGreaterThanOrEqual(0);
        expect(mock$.mock.results[idx].value.show).toHaveBeenCalled();
    });

    test('show_results=false: #analysis-results is not queried', async () => {
        await callTmf(makeEntries('frame_0000.jpg'), null, {}, false);
        const idx = mock$.mock.calls.findIndex(args => args[0] === '#analysis-results');
        expect(idx).toBe(-1);
    });

    // G. did_onload_callback ───────────────────────────────────────────────────
    test('resizes canvas and video when metadata has no dimensions and image has valid natural size', async () => {
        const tc = await callTmf(makeEntries('frame_0000.jpg'), null, { width: null, height: null });
        jest.clearAllMocks();
        tc.did_onload_callback({ img: { naturalWidth: 640, naturalHeight: 480 } });
        const canvasIdx = mock$.mock.calls.findIndex(args => args[0] && args[0].includes(' canvas'));
        const videoIdx  = mock$.mock.calls.findIndex(args => args[0] && args[0].includes(' video'));
        expect(canvasIdx).toBeGreaterThanOrEqual(0);
        expect(videoIdx).toBeGreaterThanOrEqual(0);
        expect(mock$.mock.results[canvasIdx].value.attr).toHaveBeenCalledWith('width', 640);
        expect(mock$.mock.results[videoIdx].value.attr).toHaveBeenCalledWith('height', 480);
    });

    test('does not resize when metadata already has dimensions', async () => {
        const tc = await callTmf(makeEntries('frame_0000.jpg'), null, { width: 200, height: 150 });
        jest.clearAllMocks();
        tc.did_onload_callback({ img: { naturalWidth: 640, naturalHeight: 480 } });
        const canvasIdx = mock$.mock.calls.findIndex(args => args[0] && args[0].includes(' canvas'));
        expect(canvasIdx).toBe(-1);
    });

    test('does not resize when natural dimensions are 0', async () => {
        const tc = await callTmf(makeEntries('frame_0000.jpg'), null, { width: null, height: null });
        jest.clearAllMocks();
        tc.did_onload_callback({ img: { naturalWidth: 0, naturalHeight: 0 } });
        const canvasIdx = mock$.mock.calls.findIndex(args => args[0] && args[0].includes(' canvas'));
        expect(canvasIdx).toBe(-1);
    });

    test('does not resize when imgStack is null', async () => {
        const tc = await callTmf(makeEntries('frame_0000.jpg'), null, { width: null, height: null });
        jest.clearAllMocks();
        tc.did_onload_callback(null);
        const canvasIdx = mock$.mock.calls.findIndex(args => args[0] && args[0].includes(' canvas'));
        expect(canvasIdx).toBe(-1);
    });
});

// ── trace_movie ───────────────────────────────────────────────────────────────
describe('trace_movie', () => {
    let capturedTc;
    let loadMovieSpy;

    beforeAll(() => {
        global.alert = jest.fn();
    });

    beforeEach(() => {
        jest.clearAllMocks();
        capturedTc = null;

        loadMovieSpy = jest.spyOn(MockMovieControllerClass.prototype, 'load_movie')
            .mockImplementation(function (frames) {
                capturedTc = this;
                this.frames = frames;
            });
    });

    afterEach(() => {
        loadMovieSpy.mockRestore();
        global.demo_mode = false;
    });

    /** Make a typical get-movie-metadata response with optional metadata overrides. */
    function makeResp(metaOverrides = {}, topOverrides = {}) {
        return {
            error: false,
            metadata: {
                movie_id: 'movie-123',
                width: null,
                height: null,
                movie_zipfile_url: null,
                last_frame_tracked: -1,
                total_frames: 0,
                rotation: 0,
                ...metaOverrides,
            },
            frames: {},
            ...topOverrides,
        };
    }

    /**
     * Configure mockPost so the done() callback fires synchronously with `resp`,
     * letting us test trace_movie's behaviour without real async I/O.
     */
    function mockApiResponse(resp) {
        mockPost.mockReturnValueOnce({
            done: jest.fn().mockImplementation(cb => {
                cb(resp);
                return { fail: jest.fn().mockReturnThis() };
            }),
            fail: jest.fn().mockReturnThis(),
        });
    }

    // A. API call ──────────────────────────────────────────────────────────────
    test('calls $.post with the get-movie-metadata endpoint', () => {
        mockApiResponse(makeResp());
        trace_movie('div#tracer', 'movie-123', 'my-api-key');
        expect(mockPost).toHaveBeenCalledWith(
            expect.stringContaining('get-movie-metadata'),
            expect.objectContaining({ movie_id: 'movie-123', api_key: 'my-api-key' })
        );
    });

    test('passes frame_start=0 to the API', () => {
        mockApiResponse(makeResp());
        trace_movie('div#tracer', 'movie-123', 'my-api-key');
        expect(mockPost).toHaveBeenCalledWith(
            expect.any(String),
            expect.objectContaining({ frame_start: 0 })
        );
    });

    // B. Error handling ────────────────────────────────────────────────────────
    test('alerts with the server message when resp.error is true', () => {
        mockApiResponse({ error: true, message: 'Not authorised' });
        trace_movie('div#tracer', 'movie-123', 'api-key');
        expect(global.alert).toHaveBeenCalledWith('Not authorised');
    });

    test('does not create a TracerController when resp.error is true', () => {
        mockApiResponse({ error: true, message: 'Fail' });
        trace_movie('div#tracer', 'movie-123', 'api-key');
        expect(capturedTc).toBeNull();
    });

    // C. Canvas resize from metadata ───────────────────────────────────────────
    test('sets canvas width/height when metadata has valid dimensions', () => {
        mockApiResponse(makeResp({ width: 320, height: 240 }));
        trace_movie('div#tracer', 'movie-123', 'api-key');
        // trace_movie uses .prop(); TracerController constructor uses .attr() — distinguishable
        const idx = mock$.mock.calls.findIndex(
            (args, i) => args[0] === 'div#tracer canvas' &&
                mock$.mock.results[i].value.prop.mock.calls.some(c => c[0] === 'width' && c[1] === 320)
        );
        expect(idx).toBeGreaterThanOrEqual(0);
    });

    test('does not call canvas .prop resize when metadata dimensions are null', () => {
        mockApiResponse(makeResp({ width: null, height: null }));
        trace_movie('div#tracer', 'movie-123', 'api-key');
        const propResizeCalled = mock$.mock.calls.some(
            (args, i) => args[0] === 'div#tracer canvas' &&
                mock$.mock.results[i].value.prop.mock.calls.some(c => c[0] === 'width')
        );
        expect(propResizeCalled).toBe(false);
    });

    // D. No-zip path: trace_movie_one_frame ────────────────────────────────────
    test('when no movie_zipfile_url: creates a TracerController with one frame', () => {
        mockApiResponse(makeResp());
        trace_movie('div#tracer', 'movie-123', 'api-key');
        expect(capturedTc).not.toBeNull();
        expect(capturedTc.frames).toHaveLength(1);
    });

    test('frame0 URL contains the movie_id and api_key', () => {
        mockApiResponse(makeResp());
        trace_movie('div#tracer', 'movie-123', 'my-api-key');
        expect(capturedTc.frames[0].frame_url).toContain('movie_id=movie-123');
        expect(capturedTc.frames[0].frame_url).toContain('api_key=my-api-key');
    });

    test('no-zip + non-demo mode: status asks user to place markers', () => {
        mockApiResponse(makeResp());
        trace_movie('div#tracer', 'movie-123', 'api-key');
        const idx = mock$.mock.calls.findLastIndex(args => args[0] === '#status-big');
        expect(mock$.mock.results[idx].value.html)
            .toHaveBeenCalledWith(expect.stringContaining('Place markers'));
    });

    test('no-zip + demo mode: status says "Movie ready for tracing."', () => {
        global.demo_mode = true;
        mockApiResponse(makeResp());
        trace_movie('div#tracer', 'movie-123', 'api-key');
        const idx = mock$.mock.calls.findLastIndex(args => args[0] === '#status-big');
        expect(mock$.mock.results[idx].value.html)
            .toHaveBeenCalledWith('Movie ready for tracing.');
    });

    test('no-zip path: unzip is NOT called', () => {
        mockApiResponse(makeResp());
        trace_movie('div#tracer', 'movie-123', 'api-key');
        expect(mockUnzip).not.toHaveBeenCalled();
    });

    // E. Zip path: trace_movie_frames ──────────────────────────────────────────
    test('when movie_zipfile_url present: calls trace_movie_frames (unzip invoked)', () => {
        mockUnzip.mockResolvedValueOnce({ entries: {} });
        mockApiResponse(makeResp({ movie_zipfile_url: 'http://example.com/movie.zip' }));
        trace_movie('div#tracer', 'movie-123', 'api-key');
        expect(mockUnzip).toHaveBeenCalledWith('http://example.com/movie.zip');
    });

    test('zip path: trace_movie_one_frame NOT called (unzip called, load_movie not called sync)', () => {
        mockUnzip.mockResolvedValueOnce({ entries: {} });
        mockApiResponse(makeResp({ movie_zipfile_url: 'http://example.com/movie.zip' }));
        trace_movie('div#tracer', 'movie-123', 'api-key');
        // load_movie is called inside trace_movie_frames which is async — not yet called here
        expect(capturedTc).toBeNull();
    });

    test('zip + non-demo + tracked: status says "Movie is traced!"', () => {
        mockUnzip.mockResolvedValueOnce({ entries: {} });
        mockApiResponse(makeResp({ movie_zipfile_url: 'http://example.com/movie.zip', last_frame_tracked: 5, total_frames: 10 }));
        trace_movie('div#tracer', 'movie-123', 'api-key');
        const idx = mock$.mock.calls.findLastIndex(args => args[0] === '#status-big');
        expect(mock$.mock.results[idx].value.html)
            .toHaveBeenCalledWith(expect.stringContaining('Movie is traced!'));
    });

    test('zip + non-demo + not tracked: status says "Movie ready for tracing"', () => {
        mockUnzip.mockResolvedValueOnce({ entries: {} });
        mockApiResponse(makeResp({ movie_zipfile_url: 'http://example.com/movie.zip' }));
        trace_movie('div#tracer', 'movie-123', 'api-key');
        const idx = mock$.mock.calls.findLastIndex(args => args[0] === '#status-big');
        expect(mock$.mock.results[idx].value.html)
            .toHaveBeenCalledWith(expect.stringContaining('Movie ready for tracing'));
    });

    test('zip + demo + tracked: status says exactly "Movie is traced!"', () => {
        global.demo_mode = true;
        mockUnzip.mockResolvedValueOnce({ entries: {} });
        mockApiResponse(makeResp({ movie_zipfile_url: 'http://example.com/movie.zip', last_frame_tracked: 5, total_frames: 10 }));
        trace_movie('div#tracer', 'movie-123', 'api-key');
        const idx = mock$.mock.calls.findLastIndex(args => args[0] === '#status-big');
        expect(mock$.mock.results[idx].value.html).toHaveBeenCalledWith('Movie is traced!');
    });

    test('zip + demo + not tracked: status says exactly "Movie ready for tracing."', () => {
        global.demo_mode = true;
        mockUnzip.mockResolvedValueOnce({ entries: {} });
        mockApiResponse(makeResp({ movie_zipfile_url: 'http://example.com/movie.zip' }));
        trace_movie('div#tracer', 'movie-123', 'api-key');
        const idx = mock$.mock.calls.findLastIndex(args => args[0] === '#status-big');
        expect(mock$.mock.results[idx].value.html).toHaveBeenCalledWith('Movie ready for tracing.');
    });

    // F. Play-trigger wiring ───────────────────────────────────────────────────
    test('wires up the demo-popup close button', () => {
        mockApiResponse(makeResp());
        trace_movie('div#tracer', 'movie-123', 'api-key');
        const idx = mock$.mock.calls.findIndex(args => args[0] === '#demo-popup-close');
        expect(idx).toBeGreaterThanOrEqual(0);
        expect(mock$.mock.results[idx].value.on).toHaveBeenCalledWith('click', expect.any(Function));
    });

    test('wires up the .status-big-play-trigger click handler on document', () => {
        mockApiResponse(makeResp());
        trace_movie('div#tracer', 'movie-123', 'api-key');
        const docIdx = mock$.mock.calls.findIndex(args => args[0] === document);
        expect(docIdx).toBeGreaterThanOrEqual(0);
        expect(mock$.mock.results[docIdx].value.on)
            .toHaveBeenCalledWith('click', '.status-big-play-trigger', expect.any(Function));
    });
});

// ── TracerController.track_to_end ─────────────────────────────────────────────
describe('TracerController.track_to_end', () => {
    let tc;

    beforeEach(() => {
        jest.useFakeTimers();
        global.fetch = jest.fn();
        global.alert = jest.fn();
        tc = new TracerController('div#tracer', makeMovieMetadata(), 'test-api-key');
        // Wipe constructor side-effects so assertions only cover track_to_end()
        jest.clearAllMocks();
    });

    afterEach(() => {
        jest.useRealTimers();
    });

    /** Mock fetch to resolve once with a given HTTP status and JSON body. */
    function mockFetchResponse(status, data) {
        global.fetch.mockResolvedValueOnce({
            status,
            json: () => Promise.resolve(data),
        });
    }

    /** Mock fetch to reject once with an Error. */
    function mockFetchNetworkError(message = 'Network failure') {
        global.fetch.mockRejectedValueOnce(new Error(message));
    }

    // A. Synchronous immediate effects ────────────────────────────────────────
    test('sets #status-big to "Movie is being traced..."', () => {
        mockFetchResponse(200, {});
        tc.track_to_end();
        const idx = mock$.mock.calls.findIndex(args => args[0] === '#status-big');
        expect(idx).toBeGreaterThanOrEqual(0);
        expect(mock$.mock.results[idx].value.html).toHaveBeenCalledWith('Movie is being traced...');
    });

    test('adds tracing-dimmed class to the controller div', () => {
        mockFetchResponse(200, {});
        tc.track_to_end();
        const idx = mock$.mock.calls.findIndex(args => args[0] === tc.div_selector);
        expect(idx).toBeGreaterThanOrEqual(0);
        expect(mock$.mock.results[idx].value.addClass).toHaveBeenCalledWith('tracing-dimmed');
    });

    test('sets tracking_status text to "Asking pipeline to trace movie..."', () => {
        mockFetchResponse(200, {});
        tc.track_to_end();
        expect(tc.tracking_status.text).toHaveBeenCalledWith('Asking pipeline to trace movie...');
    });

    test('disables the track button immediately', () => {
        mockFetchResponse(200, {});
        tc.track_to_end();
        expect(tc.track_button.prop).toHaveBeenCalledWith('disabled', true);
    });

    test('sets this.tracking = true', () => {
        mockFetchResponse(200, {});
        tc.track_to_end();
        expect(tc.tracking).toBe(true);
    });

    test('resets poll_error_count to 0', () => {
        mockFetchResponse(200, {});
        tc.poll_error_count = 99;
        tc.track_to_end();
        expect(tc.poll_error_count).toBe(0);
    });

    // B. fetch call ────────────────────────────────────────────────────────────
    test('POSTs to the Lambda resize-api/v1/trace-movie endpoint', () => {
        mockFetchResponse(200, {});
        tc.track_to_end();
        expect(global.fetch).toHaveBeenCalledWith(
            expect.stringContaining('resize-api/v1/trace-movie'),
            expect.objectContaining({ method: 'POST' })
        );
    });

    test('sends the api_key in the x-api-key header', () => {
        mockFetchResponse(200, {});
        tc.track_to_end();
        expect(global.fetch).toHaveBeenCalledWith(
            expect.any(String),
            expect.objectContaining({
                headers: expect.objectContaining({ 'x-api-key': 'test-api-key' }),
            })
        );
    });

    test('body includes movie_id and frame_start matching current frame_number', () => {
        mockFetchResponse(200, {});
        tc.frame_number = 7;
        tc.track_to_end();
        const body = JSON.parse(global.fetch.mock.calls[0][1].body);
        expect(body.movie_id).toBe('test-movie-001');
        expect(body.frame_start).toBe(7);
    });

    // C. Success (2xx) ─────────────────────────────────────────────────────────
    test('on 200 success: tracking remains true', async () => {
        mockFetchResponse(200, { error: false });
        tc.track_to_end();
        await jest.runAllTimersAsync();
        expect(tc.tracking).toBe(true);
    });

    test('on 200 success: no alert is fired', async () => {
        mockFetchResponse(200, { error: false });
        tc.track_to_end();
        await jest.runAllTimersAsync();
        expect(global.alert).not.toHaveBeenCalled();
    });

    test('on 200 success: tracing-dimmed is NOT removed', async () => {
        mockFetchResponse(200, { error: false });
        tc.track_to_end();
        await jest.runAllTimersAsync();
        const dimmedRemoved = mock$.mock.calls.some(
            (_, i) => mock$.mock.results[i].value.removeClass.mock.calls
                .some(c => c[0] === 'tracing-dimmed')
        );
        expect(dimmedRemoved).toBe(false);
    });

    test('on 200 success: fetch is called exactly once (no retry)', async () => {
        mockFetchResponse(200, { error: false });
        tc.track_to_end();
        await jest.runAllTimersAsync();
        expect(global.fetch).toHaveBeenCalledTimes(1);
    });

    // D. Non-retryable failure (4xx) ───────────────────────────────────────────
    test('on 400: sets tracking = false', async () => {
        mockFetchResponse(400, { error: true, message: 'Bad request' });
        tc.track_to_end();
        await jest.runAllTimersAsync();
        expect(tc.tracking).toBe(false);
    });

    test('on 400: alerts with the server error message', async () => {
        mockFetchResponse(400, { error: true, message: 'Bad request' });
        tc.track_to_end();
        await jest.runAllTimersAsync();
        expect(global.alert).toHaveBeenCalledWith('Bad request');
    });

    test('on 400: removes tracing-dimmed', async () => {
        mockFetchResponse(400, { error: true, message: 'Bad request' });
        tc.track_to_end();
        await jest.runAllTimersAsync();
        const dimmedRemoved = mock$.mock.calls.some(
            (_, i) => mock$.mock.results[i].value.removeClass.mock.calls
                .some(c => c[0] === 'tracing-dimmed')
        );
        expect(dimmedRemoved).toBe(true);
    });

    test('on 400: re-enables the track button via enableTrackButtonIfAllowed', async () => {
        mockFetchResponse(400, { error: true, message: 'Bad request' });
        tc.track_to_end();
        await jest.runAllTimersAsync();
        expect(tc.track_button.prop).toHaveBeenCalledWith('disabled', false);
    });

    test('on 400: only one fetch attempt (no retry for client errors)', async () => {
        mockFetchResponse(400, { error: true, message: 'Bad request' });
        tc.track_to_end();
        await jest.runAllTimersAsync();
        expect(global.fetch).toHaveBeenCalledTimes(1);
    });

    test('on 400: sets tracking_status to the error message', async () => {
        mockFetchResponse(400, { error: true, message: 'Bad request' });
        tc.track_to_end();
        await jest.runAllTimersAsync();
        expect(tc.tracking_status.text).toHaveBeenCalledWith('Bad request');
    });

    // E. Retryable 5xx failure ─────────────────────────────────────────────────
    test('on 500: retries exactly 3 times total before giving up', async () => {
        global.fetch.mockResolvedValue({
            status: 500,
            json: () => Promise.resolve({ error: true, message: 'Server error' }),
        });
        tc.track_to_end();
        await jest.runAllTimersAsync();
        expect(global.fetch).toHaveBeenCalledTimes(3);
    });

    test('on 500: alerts after all retries are exhausted', async () => {
        global.fetch.mockResolvedValue({
            status: 500,
            json: () => Promise.resolve({ error: true, message: 'Server error' }),
        });
        tc.track_to_end();
        await jest.runAllTimersAsync();
        expect(global.alert).toHaveBeenCalledWith('Server error');
    });

    test('on 500: sets tracking = false after final failure', async () => {
        global.fetch.mockResolvedValue({
            status: 500,
            json: () => Promise.resolve({ error: true, message: 'Server error' }),
        });
        tc.track_to_end();
        await jest.runAllTimersAsync();
        expect(tc.tracking).toBe(false);
    });

    test('on 500 then success: succeeds on second attempt, no alert', async () => {
        global.fetch
            .mockResolvedValueOnce({ status: 500, json: () => Promise.resolve({ error: true, message: 'Transient' }) })
            .mockResolvedValueOnce({ status: 200, json: () => Promise.resolve({ error: false }) });
        tc.track_to_end();
        await jest.runAllTimersAsync();
        expect(global.fetch).toHaveBeenCalledTimes(2);
        expect(global.alert).not.toHaveBeenCalled();
    });

    // F. Network error (.catch path) ───────────────────────────────────────────
    test('on network error: retries exactly 3 times total', async () => {
        global.fetch.mockRejectedValue(new Error('Network failure'));
        tc.track_to_end();
        await jest.runAllTimersAsync();
        expect(global.fetch).toHaveBeenCalledTimes(3);
    });

    test('on network error: alerts with the error message after all retries', async () => {
        global.fetch.mockRejectedValue(new Error('Network failure'));
        tc.track_to_end();
        await jest.runAllTimersAsync();
        expect(global.alert).toHaveBeenCalledWith('Network failure');
        expect(tc.tracking).toBe(false);
    });

    test('on network error with no message: alerts with fallback text', async () => {
        global.fetch.mockRejectedValue(null);
        tc.track_to_end();
        await jest.runAllTimersAsync();
        expect(global.alert).toHaveBeenCalledWith('Tracking request failed.');
    });

    test('on network error then success: succeeds on second attempt, no alert', async () => {
        global.fetch
            .mockRejectedValueOnce(new Error('Transient'))
            .mockResolvedValueOnce({ status: 200, json: () => Promise.resolve({ error: false }) });
        tc.track_to_end();
        await jest.runAllTimersAsync();
        expect(global.fetch).toHaveBeenCalledTimes(2);
        expect(global.alert).not.toHaveBeenCalled();
    });
});

export {};
