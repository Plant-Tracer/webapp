/**
 * @jest-environment jsdom
 */

const $ = require('jquery');
global.$ = $;

const module = require('users')
const bulk_register_users_func = module.bulk_register_users

describe('bulk_register_users_func', () => {
    const api_key = 'test_api_key';
    const user_primary_course_id = 1;

    beforeEach(() => {
        document.body.innerHTML = `
            <input id="br_email_addresses" value="" />
            <div id="message"></div>
        `;
        jest.clearAllMocks();
        const location = new URL('http://example.com/');
        delete window.location;
        window.location = location;

        global.planttracer_endpoint = 'some_endpoint'
        global.API_BASE = 'http://example.com/'
        global.api_key = api_key;
        global.user_primary_course_id = user_primary_course_id;
    });

    test('should show message if no email adressess are provided', () => {

        $('#br_email_addresses').val('');

        bulk_register_users_func();

        expect($('#message').html()).toBe("<b>Please provide a list of email addresses</b>");
    });


    test('should handle successful registration response', () => {
        fetch.mockResponseOnce(JSON.stringify({ error: false, message: "Registered 1 email addresses" }));

        $('#br_email_addresses').val('test@example.com');

        bulk_register_users_func();

//        expect($('#message').html()).toBe('Registered 1 email addresses');

        expect(fetch).toHaveBeenCalledWith(`${API_BASE}api/bulk-register`, expect.objectContaining({
            method: 'POST',
            body: expect.any(FormData),
        }));

        const formData = fetch.mock.calls[0][1].body;
        expect(formData.get("api_key")).toBe(api_key);
        expect(formData.get("course_id")).toBe(user_primary_course_id + "");
/*
        ToDo: how to test this window.origin stuff?
        expect(formData.get("planttracer_endpoint")).toBe(window.origin + "");
*/
    });

    test('should handle invalid email response', () => {
        fetch.mockResponseOnce(JSON.stringify({ error: false, message: "Invalid email address" }));

        $('#br_email_addresses').val('missingdomain@.com');

        bulk_register_users_func();

        //ToDo: expect($('#message').html()).toBe('error: Invalid email address');
        expect(fetch).toHaveBeenCalledWith(`${API_BASE}api/bulk-register`, expect.objectContaining({
            method: 'POST',
            body: expect.any(FormData),
        }));
    });

});
