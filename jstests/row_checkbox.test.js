/**
 * @jest-environment jsdom
 */


const $ = require('jquery');
global.$ = $;

const module = require('../static/planttracer.js')
const row_checkbox_clicked = module.row_checkbox_clicked

global.Audio = function() {
  this.play = jest.fn();
};


describe('row_checkbox_clicked', () => {
    let mockGetAttribute, mockChecked;
    beforeAll(() => {
        global.API_BASE = 'http://mock-api-base/';
        global.planttracer_endpoint = 'mock-endpoint';
        global.api_key = 'abcdefghijklmnopqrstuvwxyz'
    });
    beforeEach(() => {
        // Mock the getAttribute method on the event target
        mockGetAttribute = jest.fn();
        mockChecked = false;

        // Mock the event target element
        const mockElement = {
            getAttribute: mockGetAttribute,
            checked: mockChecked,
        };

        // Mock set_property to check if it's called with the correct values
        global.set_property = jest.fn();

        // Return the mocked element when the function is called
        global.e = mockElement;
    });

    test('calls set_property with the correct arguments when checkbox is checked', () => {
        // Arrange
        mockGetAttribute.mockImplementation((attr) => {
            switch (attr) {
                case 'x-user_id': return 'user123';
                case 'x-movie_id': return 'movie456';
                case 'x-property': return 'watched';
                default: return null;
            }
        });
        mockChecked = true; // Simulate checkbox being checked

        // Act
        row_checkbox_clicked(global.e);

        // Assert
        expect(set_property).toHaveBeenCalledWith('user123', 'movie456', 'watched', 1);
    });

    test('calls set_property with the correct arguments when checkbox is unchecked', () => {
        // Arrange
        mockGetAttribute.mockImplementation((attr) => {
            switch (attr) {
                case 'x-user_id': return 'user789';
                case 'x-movie_id': return 'movie101';
                case 'x-property': return 'favorite';
                default: return null;
            }
        });
        mockChecked = false; // Simulate checkbox being unchecked

        // Act
        row_checkbox_clicked(global.e);

        // Assert
        expect(set_property).toHaveBeenCalledWith('user789', 'movie101', 'favorite', 0);
    });
});
