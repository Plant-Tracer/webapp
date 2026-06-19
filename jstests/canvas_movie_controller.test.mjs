/* eslint-env jest, node, es6 */
/**
 * @jest-environment jsdom
 */

import { jest } from '@jest/globals';
import fs from 'fs';
import path from 'path';

const makeEl = () => ({
    off: jest.fn().mockReturnThis(),
    on: jest.fn().mockReturnThis(),
    prop: jest.fn().mockReturnThis(),
    val: jest.fn().mockReturnThis(),
    text: jest.fn().mockReturnThis(),
});

const elementBySelector = new Map();
function el(selector) {
    if (!elementBySelector.has(selector)) {
        elementBySelector.set(selector, makeEl());
    }
    return elementBySelector.get(selector);
}

function elementMatching(pattern) {
    for (const [selector, element] of elementBySelector.entries()) {
        if (selector.includes(pattern)) {
            return element;
        }
    }
    throw new Error(`No mocked element selector contains ${pattern}`);
}

const mock$ = jest.fn(selector => el(selector));

class MockCanvasController {
    constructor() {
        this.objects = [];
    }
    add_object(obj) { this.objects.push(obj); }
    clear_objects() { this.objects = []; }
    redraw() {}
}

class MockWebImage {
    constructor(_x, _y, url) {
        this.url = url;
    }
}

class MockText {
    constructor(_x, _y, text) {
        this.text = text;
    }
}

function loadMovieController() {
    const sourcePath = path.join(process.cwd(), 'src/app/static/canvas_movie_controller.js');
    const source = fs.readFileSync(sourcePath, 'utf8')
        .replace(/^import .*;\n/gm, '')
        .replace(/^export \{ MovieController \};\s*$/m, 'return MovieController;');
    return new Function('$', 'CanvasController', 'WebImage', 'Text', source)( // eslint-disable-line no-new-func
        mock$,
        MockCanvasController,
        MockWebImage,
        MockText
    );
}

const MovieController = loadMovieController();

class TrimmedMovieController extends MovieController {
    play_lower_bound() { return 2; }
    play_upper_bound() { return 4; }
}

function makeController() {
    elementBySelector.clear();
    mock$.mockClear();
    const controller = new TrimmedMovieController('div#movie');
    controller.frames = Array.from(
        { length: 6 },
        (_value, index) => ({ frame_url: `frame-${index}.jpg`, markers: [] })
    );
    controller.frame_number = 0;
    return controller;
}

afterEach(() => {
    jest.useRealTimers();
});

describe('MovieController trim play bounds', () => {
    test('play forward jumps from before lower bound to lower bound', () => {
        jest.useFakeTimers();
        const controller = makeController();
        controller.frame_number = 0;

        controller.play(1);

        expect(controller.frame_number).toBe(2);
        clearTimeout(controller.timer);
    });

    test('play reverse jumps from after upper bound to upper bound', () => {
        jest.useFakeTimers();
        const controller = makeController();
        controller.frame_number = 5;

        controller.play(-1);

        expect(controller.frame_number).toBe(4);
        clearTimeout(controller.timer);
    });

    test('loop forward wraps to lower bound instead of frame zero', () => {
        jest.useFakeTimers();
        const controller = makeController();
        controller.loop = true;
        controller.frame_number = 4;

        controller.play(1);

        expect(controller.frame_number).toBe(2);
        clearTimeout(controller.timer);
    });

    test('bounce reverse turns around inside the bounded range', () => {
        jest.useFakeTimers();
        const controller = makeController();
        controller.bounce = true;
        controller.frame_number = 2;

        controller.play(-1);

        expect(controller.frame_number).toBe(3);
        expect(controller.playing).toBe(-1);
        jest.advanceTimersByTime(100);
        expect(controller.playing).toBe(1);
        expect(controller.frame_number).toBe(4);
        clearTimeout(controller.timer);
    });

    test('control buttons use subclass play bounds', () => {
        const controller = makeController();
        controller.frame_number = 4;

        controller.set_movie_control_buttons();

        expect(elementMatching('play_forward').prop).toHaveBeenCalledWith('disabled', true);
        expect(elementMatching('play_reverse').prop).toHaveBeenCalledWith('disabled', false);
    });
});
