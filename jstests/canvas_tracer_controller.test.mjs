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
    trace_movie_one_frame,
} = await import('canvas_tracer_controller.mjs');

// Also grab the mocked Marker/Line classes for use in tests
const { Marker: MockMarkerClass, Line: MockLineClass } = await import('canvas_controller.mjs');

// Grab MockMovieController so we can spy on its prototype in trace_movie_one_frame tests
const { MovieController: MockMovieControllerClass } = await import('canvas_movie_controller.js');

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

export {};
