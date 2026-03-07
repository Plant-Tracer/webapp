/**
 * @jest-environment jsdom
 */

const { $ } = require('utils');
const fs = require('fs');
const path = require('path');

const module = require('planttracer');
const list_users_data = module.list_users_data;

global.Audio = function() {
  this.play = jest.fn();
};

// Load user data from globals.json
let userData;
beforeAll(() => {
  // Use path.join to resolve the correct path to globals.json
  const jsonPath = path.join(__dirname, 'users.json');
  userData = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
});

describe('list_users_data', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    document.body.innerHTML = '<div id="your-users"></div>';
  });

  test('should create the correct HTML for active users', () => {
    const course_array = { 1: { course_id: 1, course_name: 'Course 1' } };
    const users = [
      {
        user_id: parseInt(userData.user1.user_id, 10),
        user_name: userData.user1.name,
        email: userData.user1.email,
        primary_course_id: 1,
        first: parseInt(userData.user1.date_joined, 10),
        last: parseInt(userData.user1.last_login, 10),
      },
    ];

    list_users_data(users, course_array);

    const html = document.getElementById('your-users').innerHTML;
    expect(html).toContain(`<td>${userData.user1.name} (${userData.user1.user_id}) </td><td>${userData.user1.email}</td>`);
  });

  test('should correctly classify and display inactive users', () => {
    const course_array = { 1: { course_id: 1, course_name: 'Course 1' } };
    const users = [
      {
        user_id: parseInt(userData.user1.user_id, 10),
        user_name: userData.user1.name,
        email: userData.user1.email,
        primary_course_id: 1,
        first: parseInt(userData.user1.date_joined, 10),
        last: parseInt(userData.user1.last_login, 10),
      },
      {
        user_id: parseInt(userData.user2.user_id, 10),
        user_name: userData.user2.name,
        email: userData.user2.email,
        primary_course_id: 1,
        first: parseInt(userData.user2.date_joined, 10),
        last: parseInt(userData.user2.last_login, 10),
      },
    ];

    list_users_data(users, course_array);

    const html = document.getElementById('your-users').innerHTML;
    expect(html).toContain(`<td>${userData.user1.name} (${userData.user1.user_id}) </td><td>${userData.user1.email}</td>`);
    expect(html).toContain(`<td>${userData.user2.name} (${userData.user2.user_id}) </td><td>${userData.user2.email}</td>`);
  });

  test('should display a link to invite users for admins', () => {
    const users = [];
    global.admin = true;

    list_users_data(users, {});

    const html = document.getElementById('your-users').innerHTML;
    expect(html).toContain('<table><tbody></tbody>');
  });

  test('should not display invite link for non-admin users', () => {
    const users = [];
    global.admin = false;

    list_users_data(users, {});

    const html = document.getElementById('your-users').innerHTML;
    expect(html).not.toContain('Click here to invite a user');
  });
});
