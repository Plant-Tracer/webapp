/**
 * @jest-environment jsdom
 */

const { $ } = require('utils');
const module = require('users')
const bulk_register_users_func = module.bulk_register_users

describe('bulk_register_users_func', () => {

    beforeEach(() => {
        jest.clearAllMocks();
        global.planttracer_endpoint = 'some_endpoint'
        global.API_BASE = 'http://example.com/'
        global.api_key = 'test_api_key';
        global.user_primary_course_id = 1;

      // Add the mock DOM elements the function expects to find

        document.body.innerHTML = `
            <textarea id="br_email_addresses"></textarea>
            <div id="message"></div>
        `;    });

    test('should show message if no email adressess are provided', () => {

        $('#br_email_addresses').val('');

        bulk_register_users_func();

        expect($('#message').html()).toBe("<b>Please provide a list of email addresses</b>");
    });


    test('should handle successful registration response', () => {
        $.post = jest.fn().mockImplementation((_url, _payload) => ({
            done: function (callback) {
                callback({ error: false, message: "Registered 1 email addresses" });
                return this;
            },
            fail: jest.fn().mockReturnThis(),
        }));

        $('#br_email_addresses').val('test@example.com');

        bulk_register_users_func();

        expect($.post).toHaveBeenCalledWith(`${API_BASE}api/bulk-register`, {
            api_key,
            planttracer_endpoint: window.origin + "",
            course_id: user_primary_course_id,
            "email-addresses": 'test@example.com',
        });
        expect($('#message').html()).toBe('Registered 1 email addresses');
    });

    test('should handle invalid email response', () => {
        $.post = jest.fn().mockImplementation((_url, _payload) => ({
            done: function (callback) {
                callback({ error: true, message: "Invalid email address" });
                return this;
            },
            fail: jest.fn().mockReturnThis(),
        }));

        $('#br_email_addresses').val('missingdomain@.com');

        bulk_register_users_func();

        expect($.post).toHaveBeenCalledWith(`${API_BASE}api/bulk-register`, {
            api_key,
            planttracer_endpoint: window.origin + "",
            course_id: user_primary_course_id,
            "email-addresses": 'missingdomain@.com',
        });
        expect($('#message').html()).toBe('error: Invalid email address');
    });

});
