/**
 * @jest-environment jsdom
 */

global.resend_func_mockVal = jest.fn();
global.resend_func_mockHtml = jest.fn();
global.resend_func_mockPost = jest.fn();
const noop = () => {};
const noopChain = { html: noop, val: noop, prop: noop, click: noop, show: noop, hide: noop, on: noop };
const mock$Fn = jest.fn((selector) => {
    if (selector && selector.nodeType === 9) return { ready: (cb) => cb() };
    if (selector === '#email') return { val: global.resend_func_mockVal };
    if (selector === '#message') return { html: global.resend_func_mockHtml };
    return noopChain;
});
mock$Fn.post = global.resend_func_mockPost;
jest.mock('utils', () => ({
    get $() { return mock$Fn; },
    $$: jest.fn(),
    DOMWrapper: jest.fn(),
}));

const module = require('planttracer');
const resend_func = module.resend_func;

global.Audio = function() {
  this.play = jest.fn();
};

describe('resend_func', () => {
    let mockVal, mockHtml;

    beforeAll(() => {
        global.API_BASE = 'https://planttracer.com';
        global.planttracer_endpoint = 'test-endpoint';
    });

    beforeEach(() => {
        mockVal = global.resend_func_mockVal;
        mockHtml = global.resend_func_mockHtml;
        mockVal.mockClear();
        mockHtml.mockClear();
        global.resend_func_mockPost.mockClear();
    });

    test('displays error message when email is empty', () => {
        mockVal.mockReturnValue('');

        resend_func();
        expect(mockHtml).toHaveBeenCalledWith("<b>Please provide an email address</b>");
        expect(global.resend_func_mockPost).not.toHaveBeenCalled();
    });
});
