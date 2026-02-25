/* eslint-env jest, node, es6 */
/**
 * @jest-environment jsdom
 */

import { jest } from '@jest/globals';

import { CanvasController } from 'canvas_controller.mjs';

beforeAll(() => {
    document.body.innerHTML = `
        <canvas id="zoom-test-canvas" width="100" height="100"></canvas>
        <select class="zoom-test">
            <option value="50">50%</option>
            <option value="100" selected>100%</option>
            <option value="150">150%</option>
        </select>
    `;
});

beforeEach(() => {
    localStorage.clear();
    // Reset the select to default
    document.querySelector('.zoom-test').value = '100';
});

describe('setup_zoom_storage', () => {
    test('restores valid zoom from localStorage', () => {
        localStorage.setItem('test_zoom_key', '150');
        const controller = new CanvasController('#zoom-test-canvas', '.zoom-test');
        controller.setup_zoom_storage('test_zoom_key');
        expect(controller.zoom).toBeCloseTo(1.5);
        expect(document.querySelector('.zoom-test').value).toBe('150');
    });

    test('ignores invalid zoom value from localStorage', () => {
        localStorage.setItem('test_zoom_key', '999');
        const controller = new CanvasController('#zoom-test-canvas', '.zoom-test');
        controller.setup_zoom_storage('test_zoom_key');
        expect(controller.zoom).toBe(1); // default unchanged
    });

    test('does nothing when localStorage has no saved value', () => {
        const controller = new CanvasController('#zoom-test-canvas', '.zoom-test');
        controller.setup_zoom_storage('test_zoom_key');
        expect(controller.zoom).toBe(1); // default unchanged
    });

    test('saves zoom to localStorage on select change', () => {
        const controller = new CanvasController('#zoom-test-canvas', '.zoom-test');
        controller.setup_zoom_storage('test_zoom_key');
        const selectEl = document.querySelector('.zoom-test');
        selectEl.value = '50';
        selectEl.dispatchEvent(new Event('change'));
        expect(localStorage.getItem('test_zoom_key')).toBe('50');
    });

    test('does nothing when zoom_selector is not set', () => {
        const controller = new CanvasController('#zoom-test-canvas', null);
        expect(() => controller.setup_zoom_storage('test_zoom_key')).not.toThrow();
        expect(controller.zoom).toBe(1); // default
    });

    test('uses different keys for different movies', () => {
        localStorage.setItem('analysis_zoom_movie-aaa', '50');
        localStorage.setItem('analysis_zoom_movie-bbb', '150');

        const c1 = new CanvasController('#zoom-test-canvas', '.zoom-test');
        c1.setup_zoom_storage('analysis_zoom_movie-aaa');
        expect(c1.zoom).toBeCloseTo(0.5);

        const c2 = new CanvasController('#zoom-test-canvas', '.zoom-test');
        c2.setup_zoom_storage('analysis_zoom_movie-bbb');
        expect(c2.zoom).toBeCloseTo(1.5);
    });
});

export {};
