/**
 * @jest-environment jsdom
 */


const $ = require('jquery');
global.$ = $;

const module = require('planttracer')
const check_upload_metadata = module.check_upload_metadata

global.Audio = function() {
  this.play = jest.fn();
};

describe('check_upload_metadata', () => {
    let mockVal, mockProp;

    beforeEach(() => {
        // Mock the jQuery selector function
        mockVal = jest.fn(); // Mock for val()
        mockProp = jest.fn(); // Mock for prop()

        global.$ = jest.fn((selector) => {
            if (selector === '#movie-title') {
                return { val: mockVal };
            }
            if (selector === '#movie-description') {
                return { val: mockVal };
            }
            if (selector === '#movie-file') {
                return { val: mockVal };
            }
            if (selector === '#upload-button') {
                return { prop: mockProp };
            }
        });
    });

    test('disables upload button if title is too short', () => {
        // Arrange
        mockVal.mockReturnValueOnce('ab')  // Title is too short
            .mockReturnValueOnce('Valid description')  // Valid description
            .mockReturnValueOnce('somefile.mp4');  // Movie file is selected

        // Act
        check_upload_metadata();

        // Assert
        expect(mockProp).toHaveBeenCalledWith('disabled', true); // Button should be disabled
    });

    test('disables upload button if description is too short', () => {
        // Arrange
        mockVal.mockReturnValueOnce('Valid title')  // Valid title
            .mockReturnValueOnce('ab')  // Description is too short
            .mockReturnValueOnce('somefile.mp4');  // Movie file is selected

        // Act
        check_upload_metadata();

        // Assert
        expect(mockProp).toHaveBeenCalledWith('disabled', true); // Button should be disabled
    });

    test('disables upload button if no movie file is selected', () => {
        // Arrange
        mockVal.mockReturnValueOnce('Valid title')  // Valid title
            .mockReturnValueOnce('Valid description')  // Valid description
            .mockReturnValueOnce('');  // No movie file selected

        // Act
        check_upload_metadata();

        // Assert
        expect(mockProp).toHaveBeenCalledWith('disabled', true); // Button should be disabled
    });

    test('enables upload button if all inputs are valid', () => {
        // Arrange
        mockVal.mockReturnValueOnce('Valid title')  // Valid title
            .mockReturnValueOnce('Valid description')  // Valid description
            .mockReturnValueOnce('somefile.mp4');  // Movie file is selected

        // Act
        check_upload_metadata();

        // Assert
        expect(mockProp).toHaveBeenCalledWith('disabled', false); // Button should be enabled
    });
});
