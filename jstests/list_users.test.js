/**
 * @jest-environment jsdom
 */


const $ = require('jquery');
global.$ = $;

const list_users_data = require('../static/planttracer');


global.user_id = '1'; 
global.PUBLISHED = 'published'; 
global.UNPUBLISHED = 'unpublished'; 
global.user_demo = false;
global.user_primary_course_id = '101';
global.movies_fill_div = jest.fn();



describe('list_users_data', () => {
    beforeEach(() => {
        document.body.innerHTML = `
            <div id="your-users"></div>
        `;
    });

    test('should correctly generate HTML for users with different primary courses', () => {
        const users = [
            { name: 'Johnny', user_id: '1', email: 'Johnny@example.com', first: 1625097600, last: 1627689600, primary_course_id: '101' },
            { name: 'Ruth', user_id: '2', email: 'Ruth@example.com', first: 1625097600, last: 1627689600, primary_course_id: '102' }
        ];
        const course_array = {
            '101': { course_name: 'Math' },
            '102': { course_name: 'Science' }
        };

        list_users_data(users, course_array);

        console.log($('#your-users').html()); // Debug log

        const expectedHtml = `
            <table><tbody>
            <tr><td colspan='4'>&nbsp;</td></tr>
            <tr><th colspan='4'>Primary course: Math (101)</th></tr>
            <tr><th>Name</th><th>Email</th><th>First Seen</th><th>Last Seen</th></tr>
            <tr><td>Johnny (1) </td><td>Johnny@example.com</td><td>${new Date(1625097600 * 1000).toString()}</td><td>${new Date(1627689600 * 1000).toString()}</td></tr>
            <tr><td colspan='4'>&nbsp;</td></tr>
            <tr><th colspan='4'>Primary course: Science (102)</th></tr>
            <tr><th>Name</th><th>Email</th><th>First Seen</th><th>Last Seen</th></tr>
            <tr><td>Ruth (2) </td><td>Ruth@example.com</td><td>${new Date(1625097600 * 1000).toString()}</td><td>${new Date(1627689600 * 1000).toString()}</td></tr>
            </tbody></table>
        `.trim();

        expect($('#your-users').html().trim()).toBe(expectedHtml);
    });

    test('should correctly generate HTML for users with the same primary course', () => {
        const users = [
            { name: 'Johnny', user_id: '1', email: 'Johnny@example.com', first: 1625097600, last: 1627689600, primary_course_id: '101' },
            { name: 'Ruth', user_id: '2', email: 'Ruth@example.com', first: 1625097600, last: 1627689600, primary_course_id: '101' }
        ];
        const course_array = {
            '101': { course_name: 'Math' },
            '102': { course_name: 'Science' }
        };

        list_users_data(users, course_array);

        const expectedHtml = `
            <table><tbody>
            <tr><td colspan='4'>&nbsp;</td></tr>
            <tr><th colspan='4'>Primary course: Math (101)</th></tr>
            <tr><th>Name</th><th>Email</th><th>First Seen</th><th>Last Seen</th></tr>
            <tr><td>Johnny (1) </td><td>Johnny@example.com</td><td>${new Date(1625097600 * 1000).toString()}</td><td>${new Date(1627689600 * 1000).toString()}</td></tr>
            <tr><td>Ruth (2) </td><td>Ruth@example.com</td><td>${new Date(1625097600 * 1000).toString()}</td><td>${new Date(1627689600 * 1000).toString()}</td></tr>
            </tbody></table>
        `.trim();

        expect($('#your-users').html().trim()).toBe(expectedHtml);
    });

    test('should display "n/a" for missing dates', () => {
        const users = [
            { name: 'Johnny', user_id: '1', email: 'Johnny@example.com', first: null, last: null, primary_course_id: '101' }
        ];
        const course_array = {
            '101': { course_name: 'Math' },
            '102': { course_name: 'Science' }
        };

        list_users_data(users, course_array);

        const expectedHtml = `
            <table><tbody>
            <tr><td colspan='4'>&nbsp;</td></tr>
            <tr><th colspan='4'>Primary course: Math (101)</th></tr>
            <tr><th>Name</th><th>Email</th><th>First Seen</th><th>Last Seen</th></tr>
            <tr><td>Johnny (1) </td><td>Johnny@example.com</td><td>n/a</td><td>n/a</td></tr>
            </tbody></table>
        `.trim();

        expect($('#your-users').html().trim()).toBe(expectedHtml);
    });
});