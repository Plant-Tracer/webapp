/* eslint-env jest, node, es6 */
/**
 * @jest-environment jsdom
 */

import $ from 'jquery';
global.$ = $;

import { CanvasController, CanvasItem, Marker, WebImage, Line, Text } from 'canvas_controller.mjs';
const CanvasText = Text;

beforeAll(() => {
  document.body.innerHTML = '<!doctype html><html><body><canvas id="test-canvas" width="100" height="100"></canvas></body></html>';
});

describe('CanvasController', () => {
  let controller;
  beforeEach(() => {
    controller = new CanvasController('#test-canvas', '100');
  });

  test('constructor with valid selector and PointerEvent present', () => {
    window.PointerEvent = true;
    expect(controller.c).toBeDefined();
    expect(controller.ctx).toBeDefined();
  });

  test('constructor with valid selector', () => {
    expect(controller.c).toBeDefined();
    expect(controller.ctx).toBeDefined();
  });

  test('constructor with invalid selector', () => {
    const badController = new CanvasController('#does-not-exist');
    expect(badController.c).toBeUndefined();
  });

  test('constructor with missing selector', () => {
    expect(() => new CanvasController()).not.toThrow();
  });

  test('add_object with valid object', () => {
    const obj = new CanvasItem(1, 2, 'test');
    controller.add_object(obj);
    expect(controller.objects).toContain(obj);
  });

  test('add_object with invalid object', () => {
    expect(() => controller.add_object(null)).toThrow(TypeError);
  });

  test('add_object with missing parameter', () => {
    expect(() => controller.add_object()).toThrow(TypeError);
  });

  test('clear_objects removes all objects', () => {
    const obj = new CanvasItem(1, 2, 'test');
    controller.add_object(obj);
    controller.clear_objects();
    expect(controller.objects.length).toBe(0);
  });

  test('clear_selection unselects selected object', () => {
    const obj = new CanvasItem(1, 2, 'test');
    controller.selected = obj;
    controller.clear_selection();
    expect(controller.selected).toBeNull();
  });

  test('clear_selection with no selected object', () => {
    controller.selected = null;
    controller.clear_selection();
    expect(controller.selected).toBeNull();
  });

  test('getPointerLocation with valid event', () => {
    const e = { x: 10, y: 20 };
    const pos = controller.getPointerLocation(e);
    expect(pos).toHaveProperty('x');
    expect(pos).toHaveProperty('y');
  });

  test('getPointerLocation with missing event', () => {
    expect(() => controller.getPointerLocation()).toThrow();
  });

  test('startMarkerDrag with valid event', () => {
    const obj = new CanvasItem(1, 2, 'test');
    controller.add_object(obj);
    const e = { x: 10, y: 20 };
    controller.startMarkerDrag(e);
    expect(controller.selected).toBeDefined();
  });

  test('startMarkerDrag with missing event', () => { 
    expect(() => controller.startMarkerDrag()).toThrow(Error);
  });

  test('startMarkerDrag with invalid event', () => {
    expect(() => controller.startMarkerDrag({})).toThrow(Error);
  });

  test('moveMarker with valid event', () => {
    const e = { x: 10, y: 20 };
    controller.moveMarker(e);
    expect(controller.selected).toBeDefined();
  });

  });

describe('CanvasItem', () => {
  test('constructor with valid params', () => {
    const item = new CanvasItem(1, 2, 'item');
    expect(item.x).toBe(1);
    expect(item.y).toBe(2);
    expect(item.name).toBe('item');
  });

  test('constructor with missing params', () => {
    const item = new CanvasItem();
    expect(item.x).toBeUndefined();
    expect(item.y).toBeUndefined();
    expect(item.name).toBeUndefined();
  });

  test('contains_point always false', () => {
    const item = new CanvasItem(1, 2, 'item');
    expect(item.contains_point({ x: 1, y: 2 })).toBe(false);
  });

  test('loc with valid params', () => {
    const item = new CanvasItem(1, 2, 'item');
    expect(item.loc()).toBe('(1,2)');
  });

  test('loc with missing params', () => {
    const item = new CanvasItem();
    expect(item.loc()).toBe('(NaN,NaN)');
  });
});

describe('Marker', () => {
  test('constructor with valid params', () => {
    const marker = new Marker(1, 2, 5, 'red', 'black', 'm1');
    expect(marker.x).toBe(1);
    expect(marker.y).toBe(2);
    expect(marker.r).toBe(5);
    expect(marker.fill).toBe('red');
    expect(marker.stroke).toBe('black');
    expect(marker.name).toBe('m1');
  });

  test('constructor with missing params', () => {
    const marker = new Marker();
    expect(marker.x).toBeUndefined();
    expect(marker.y).toBeUndefined();
    expect(marker.r).toBeUndefined();
  });

  test('contains_point inside and outside', () => {
    const marker = new Marker(0, 0, 10, 'red', 'black', 'm1');
    expect(marker.contains_point({ x: 0, y: 0 })).toBe(true);
    expect(marker.contains_point({ x: 20, y: 20 })).toBe(false);
  });
});

describe('Line', () => {
  test('constructor with valid params', () => {
    const line = new Line(0, 0, 10, 10, 2, 'blue');
    expect(line.x2).toBe(10);
    expect(line.y2).toBe(10);
    expect(line.width).toBe(2);
    expect(line.color).toBe('blue');
  });

  test('constructor with missing params', () => {
    const line = new Line();
    expect(line.x2).toBeUndefined();
    expect(line.y2).toBeUndefined();
  });
});

describe('CanvasText', () => {
  test('constructor with valid params', () => {
    const text = new CanvasText(1, 2, 'hello', 'green');
    expect(text.x).toBe(1);
    expect(text.y).toBe(2);
    expect(text.name).toBe('hello');
    expect(text.color).toBe('green');
  });

  test('constructor with missing params', () => {
    const text = new CanvasText();
    expect(text.x).toBeUndefined();
    expect(text.y).toBeUndefined();
    expect(text.name).toBeUndefined();
  });
});

describe('WebImage', () => {
  test('constructor with valid params', () => {
    const img = new WebImage(0, 0, 'http://example.com/image.png');
    expect(img.x).toBe(0);
    expect(img.y).toBe(0);
    expect(img.url).toBe('http://example.com/image.png');
  });

  test('constructor with missing params', () => {
    const img = new WebImage();
    expect(img.x).toBeUndefined();
    expect(img.y).toBeUndefined();
    expect(img.url).toBeUndefined();
  });
});

export {}; 