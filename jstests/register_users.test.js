/**
 * @jest-environment jsdom
 */


const $ = require('jquery');
global.$ = $;

const module = require('../static/planttracer')
const register_func = module.register_func

describe('register_func', () => {
    beforeEach(() => {
        document.body.innerHTML = `
            <input id="email" value="" />
            <input id="course_key" value="" />
            <input id="name" value="" />
            <div id="message"></div>
        `;
        jest.clearAllMocks();
    });

    test('should show message if email is not provided', () => {
        $('#course_key').val('test_course_key');
        $('#name').val('Test Name');

        register_func();

        expect($('#message').html()).toBe("<b>Please provide an email address</b>");
    });

    test('should show message if course key is not provided', () => {
        $('#email').val('test@example.com');
        $('#name').val('Test Name');

        register_func();

        expect($('#message').html()).toBe("<b>Please provide a course key</b>");
    });

    test('should show message if name is not provided', () => {
        $('#email').val('test@example.com');
        $('#course_key').val('test_course_key');

        register_func();

        expect($('#message').html()).toBe("<b>Please provide a name</b>");
    });

    test('should show asking to register message and make POST request', () => {
        $.post = jest.fn().mockImplementation(() => ({
            done: jest.fn().mockReturnThis(),
            fail: jest.fn().mockReturnThis(),
        }));
        global.planttracer_endpoint = 'some_endpoint'
        global.API_BASE = 'http://example.com/'
        $('#email').val('test@example.com');
        $('#course_key').val('test_course_key');
        $('#name').val('Test Name');

        register_func();

        expect($('#message').html()).toBe('Asking to register <b>test@example.com</b> for course key <b>test_course_key<b>...<br></b></b>');
        expect($.post).toHaveBeenCalledWith(`${API_BASE}api/register`, {
            email: 'test@example.com',
            course_key: 'test_course_key',
            planttracer_endpoint: 'some_endpoint',
            name: 'Test Name'
        });
    });

    test('should handle successful registration response', () => {
        $.post = jest.fn().mockImplementation((url, data) => ({
            done: function (callback) {
                callback({ message: 'Registration successful' });
                return this;
            },
            fail: jest.fn().mockReturnThis(),
        }));
        global.planttracer_endpoint = 'some_endpoint'
        global.API_BASE = 'http://example.com/'
        $('#email').val('test@example.com');
        $('#course_key').val('test_course_key');
        $('#name').val('Test Name');

        register_func();

        expect($('#message').html()).toBe('<b>Registration successful</b>');
    });

    test('should handle registration error response', () => {
        $.post = jest.fn().mockImplementation((url, data) => ({
            done: function (callback) {
                callback({ error: true, message: 'Error occurred' });
                return this;
            },
            fail: jest.fn().mockReturnThis(),
        }));
        global.planttracer_endpoint = 'some_endpoint'
        global.API_BASE = 'http://example.com/'
        $('#email').val('test@example.com');
        $('#course_key').val('test_course_key');
        $('#name').val('Test Name');

        register_func();

        expect($('#message').html()).toBe('<b>Error: Error occurred</b>');
    });

    test('should handle failed POST request', () => {
        $.post = jest.fn().mockImplementation((url, data) => ({
            done: jest.fn().mockReturnThis(),
            fail: function (callback) {
                callback({ responseText: 'Network error' });
                return this;
            },
        }));
        global.planttracer_endpoint = 'some_endpoint'
        global.API_BASE = 'http://example.com/'
        $('#email').val('test@example.com');
        $('#course_key').val('test_course_key');
        $('#name').val('Test Name');

        register_func();

        expect($('#message').html()).toBe('POST error: Network error');
    });
});