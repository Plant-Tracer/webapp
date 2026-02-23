/**
 * @jest-environment jsdom
 *
 * The list page (list.html) injects HTML with inline onclick handlers like
 *   onclick='play_clicked(this)' and onclick='analyze_clicked(this)'.
 * Those names are evaluated in the global (window) scope when the user clicks.
 * If they are not defined on window, the browser throws ReferenceError and
 * Play/Analyze buttons do nothing. This test ensures we never regress by
 * requiring the module to expose those handlers on the global object.
 *
 * Why didn't existing tests catch the bug? list_movies.test.js only asserts
 * on the HTML string produced by list_movies_data() (tables, labels, etc.).
 * It never checks that the handlers referenced by that HTML are defined on
 * window, and no test simulates clicking a Play/Analyze button. So the
 * "inline onclick must resolve in global scope" contract was untested.
 */
const module = require('planttracer');

describe('List page global handlers (inline onclick)', () => {
  const requiredGlobals = [
    'play_clicked',
    'analyze_clicked',
    'row_pencil_clicked',
    'action_button_clicked',
    'hide_clicked',
    'list_ready_function',
  ];

  requiredGlobals.forEach((name) => {
    it(`should expose ${name} on window for list page inline onclick`, () => {
      expect(typeof window[name]).toBe('function');
    });
  });
});
