/**
 * @jest-environment jsdom
 */


const $ = require('jquery');
global.$ = $;

const module = require('planttracer')
const resend_func = module.resend_func

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
        mockVal = jest.fn();
        mockHtml = jest.fn();

        global.$ = jest.fn((selector) => {
            if (selector === '#email') {
                return { val: mockVal };
            }
            if (selector === '#message') {
                return { html: mockHtml };
            }
        });

        $.post = jest.fn();
    });

    test('displays error message when email is empty', () => {
        mockVal.mockReturnValue('');

        resend_func();
        expect(mockHtml).toHaveBeenCalledWith("<b>Please provide an email address</b>");
        expect($.post).not.toHaveBeenCalled();
    });
});
