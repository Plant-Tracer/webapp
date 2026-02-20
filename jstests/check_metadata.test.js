/**
 * @jest-environment jsdom
 */

global.check_metadata_mockVal = jest.fn();
global.check_metadata_mockProp = jest.fn();
jest.mock('utils', () => {
    const noop = () => {};
    const noopChain = { html: noop, val: noop, prop: noop, click: noop, show: noop, hide: noop, on: noop };
    return {
    $: jest.fn((selector) => {
        if (selector && selector.nodeType === 9) {
            return { ready: (cb) => cb() };
        }
        if (['#movie-title', '#movie-description', '#movie-file'].includes(selector)) {
            return { val: global.check_metadata_mockVal };
        }
        if (selector === '#upload-button') {
            return { prop: global.check_metadata_mockProp };
        }
        return noopChain;
    }),
    $$: jest.fn(),
    DOMWrapper: jest.fn(),
};
});

const module = require('planttracer');
const check_upload_metadata = module.check_upload_metadata;

global.Audio = function() {
  this.play = jest.fn();
};

describe('check_upload_metadata', () => {
    let mockVal, mockProp;

    beforeEach(() => {
        mockVal = global.check_metadata_mockVal;
        mockProp = global.check_metadata_mockProp;
        mockVal.mockClear();
        mockProp.mockClear();
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
