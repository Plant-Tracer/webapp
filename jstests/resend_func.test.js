/**
 * @jest-environment jsdom
 */


const $ = require('jquery');
global.$ = $;

const module = require('../static/planttracer')
const resend_func = module.resend_func

global.Audio = function() {
  this.play = jest.fn();
};


describe('resend_func', () => {
    let mockVal, mockHtml;

    // Declare global variables for the API base and endpoint
    beforeAll(() => {
        global.API_BASE = 'http://mock-api-base/';
        global.planttracer_endpoint = 'mock-endpoint';
    });

    beforeEach(() => {
        // Mock the jQuery selector function
        mockVal = jest.fn(); // Mock for val()
        mockHtml = jest.fn(); // Mock for html()

        // Mock the entire jQuery $ object, including the post method
        global.$ = jest.fn((selector) => {
            if (selector === '#email') {
                return { val: mockVal };
            }
            if (selector === '#message') {
                return { html: mockHtml };
            }
        });

        // Now mock the $.post function as part of the global jQuery mock
        $.post = jest.fn();
    });

    test('displays error message when email is empty', () => {
        // Arrange
        mockVal.mockReturnValue(''); // Simulate empty email input

        // Act
        resend_func();

        // Assert
        expect(mockHtml).toHaveBeenCalledWith("<b>Please provide an email address</b>");
        expect($.post).not.toHaveBeenCalled(); // Ensure the post request is not made
    });
});
