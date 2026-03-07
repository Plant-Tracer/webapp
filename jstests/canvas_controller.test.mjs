/* eslint-env jest, node, es6 */
/**
 * @jest-environment jsdom
 */

import { jest } from '@jest/globals';

import { CanvasController, CanvasItem, Marker, WebImage, Line, Text } from 'canvas_controller.mjs';
const CanvasText = Text;

beforeAll(() => {
  document.body.innerHTML = '<canvas id="test-canvas" width="100" height="100"></canvas>';
});

describe('CanvasController', () => {
  let controller;
  beforeEach(() => {
    controller = new CanvasController('#test-canvas', null);
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

  test('should start dragging a marker', () => {
    const marker = new Marker(50, 50, 10, 'red', 'black', 'test-marker');
    controller.add_object(marker);
    
    // Create a mock event at the marker's position
    const mockEvent = {
      x: 50,
      y: 50
    };
    
    controller.startMarkerDrag(mockEvent);
    
    // Verify the marker is selected
    expect(controller.selected).toBe(marker);
    expect(controller.c.style.cursor).toBe('crosshair');
  });

  test('should move marker diagonally and end drag', () => {
    const marker = new Marker(50, 50, 10, 'red', 'black', 'test-marker');
    controller.add_object(marker);
    
    // Start dragging at original position
    const startEvent = { x: 50, y: 50 };
    controller.startMarkerDrag(startEvent);
    expect(controller.selected).toBe(marker);
    
    // Move diagonally up and right in 2-unit increments (5 moves for 10 units total)
    for (let i = 1; i <= 5; i++) {
      const moveEvent = { x: 50 + (i * 2), y: 50 - (i * 2) };
      controller.moveMarker(moveEvent);
    }
    
    // Verify final position (should be at 60, 40)
    expect(marker.x).toBe(60);
    expect(marker.y).toBe(40);
    
    // End the drag
    controller.endMarkerDrag();
    
    // Verify drag is ended
    expect(controller.selected).toBeNull();
    expect(controller.c.style.cursor).toBe('auto');
  });

  });

describe('CanvasController event handlers', () => {
  let controller;
  beforeEach(() => {
    controller = new CanvasController('#test-canvas', null);
    // Add a marker for selection/movement
    const marker = new Marker(50, 50, 10, 'red', 'black', 'test-marker');
    controller.add_object(marker);
  });

  test('mousedown_handler selects marker', () => {
    const event = { x: 50, y: 50 };
    controller.mousedown_handler(event);
    expect(controller.selected).toBeDefined();
  });

  test('mousemove_handler moves marker', () => {
    const event = { x: 50, y: 50 };
    controller.startMarkerDrag(event);
    const moveEvent = { x: 60, y: 60 };
    controller.mousemove_handler(moveEvent);
    expect(controller.selected).toBeDefined();
  });

  test('mouseup_handler ends drag', () => {
    const event = { x: 50, y: 50 };
    controller.startMarkerDrag(event);
    controller.mouseup_handler();
    expect(controller.selected).toBeNull();
  });

  test('touchstart_handler selects marker', () => {
    const event = { touches: [{ clientX: 50, clientY: 50 }], preventDefault: jest.fn() };
    controller.touchstart_handler(event);
    expect(controller.selected).toBeDefined();
  });

  test('touchmove_handler moves marker', () => {
    const startEvent = { touches: [{ clientX: 50, clientY: 50 }], preventDefault: jest.fn() };
    controller.touchstart_handler(startEvent);
    const moveEvent = { touches: [{ clientX: 60, clientY: 60 }], preventDefault: jest.fn() };
    controller.touchmove_handler(moveEvent);
    expect(controller.selected).toBeDefined();
  });

  test('touchend_handler ends drag', () => {
    const startEvent = { touches: [{ clientX: 50, clientY: 50 }], preventDefault: jest.fn() };
    controller.touchstart_handler(startEvent);
    controller.touchend_handler();
    expect(controller.selected).toBeNull();
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

  test('draw does not throw', () => {
    const line = new Line(0, 0, 10, 10, 2, 'blue');
    // Create a mock canvas context with required methods
    const ctx = {
      save: jest.fn(),
      beginPath: jest.fn(),
      lineWidth: 0,
      moveTo: jest.fn(),
      lineTo: jest.fn(),
      strokeStyle: '',
      stroke: jest.fn(),
      restore: jest.fn(),
    };
    expect(() => line.draw(ctx, false)).not.toThrow();
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

  test('draw does not throw', () => {
    const text = new CanvasText(1, 2, 'hello', 'green');
    // Create a mock canvas context with required methods
    const ctx = {
      save: jest.fn(),
      font: '',
      fillText: jest.fn(),
    };
    expect(() => text.draw(ctx, false)).not.toThrow();
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

  test('draw does not throw when loaded', () => {
    const img = new WebImage(0, 0, 'http://example.com/image.png');
    img.loaded = true;
    img.img = { naturalWidth: 100, naturalHeight: 50 };
    const ctx = {
      drawImage: jest.fn(),
      fillText: jest.fn(),
    };
    expect(() => img.draw(ctx, false)).not.toThrow();
  });

  test('draw does not throw when not loaded', () => {
    const img = new WebImage(0, 0, 'http://example.com/image.png');
    img.loaded = false;
    img.img = { src: 'http://example.com/image.png', naturalWidth: 100 };
    const ctx = {
      drawImage: jest.fn(),
      fillText: jest.fn(),
    };
    expect(() => img.draw(ctx, false)).not.toThrow();
  });
});

export {}; 