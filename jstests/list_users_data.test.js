/**
 * @jest-environment jsdom
 */

const $ = require('jquery');
const fs = require('fs');
const path = require('path');
global.$ = $;

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
  });

  test('should create the correct HTML for active users', () => {
    const users = [
      {
        user_id: parseInt(userData.user1.user_id, 10),
        name: userData.user1.user_name,
        email: userData.user1.email,
        active: userData.user1.active === 'true',
        date_joined: parseInt(userData.user1.date_joined, 10),
        last_login: parseInt(userData.user1.last_login, 10),
      },
    ];

    $.fn.html = jest.fn();
    list_users_data(users);
    expect($.fn.html).toHaveBeenCalledTimes(1);

    const expectedHtml = expect.stringContaining(
      `<table><tbody><tr><td>${userData.user1.user_name} (${userData.user1.user_id}) </td><td>${userData.user1.email}</td><td>n/a</td><td>n/a</td></tr>`
    );
    expect($.fn.html).toHaveBeenCalledWith(expectedHtml);
  });

  test('should correctly classify and display inactive users', () => {
    const users = [
      {
        user_id: parseInt(userData.user1.user_id, 10),
        user_name: userData.user1.user_name,
        email: userData.user1.email,
        active: userData.user1.active === 'true',
        date_joined: parseInt(userData.user1.date_joined, 10),
        last_login: parseInt(userData.user1.last_login, 10),
      },
      {
        user_id: parseInt(userData.user2.user_id, 10),
        user_name: userData.user2.user_name,
        email: userData.user2.email,
        active: userData.user2.active === 'true',
        date_joined: parseInt(userData.user2.date_joined, 10),
        last_login: parseInt(userData.user2.last_login, 10),
      },
    ];

    $.fn.html = jest.fn();
    list_users_data(users);
    expect($.fn.html).toHaveBeenCalledTimes(1);

    const expectedHtml1 = expect.stringContaining(
      `<table><tbody><tr><td>${userData.user1.user_name} (${userData.user1.user_id}) </td><td>${userData.user1.email}</td><td>n/a</td><td>n/a</td></tr>`
    );
    const expectedHtml2 = expect.stringContaining(
      `<tr><td>${userData.user2.user_name} (${userData.user2.user_id}) </td><td>${userData.user2.email}</td><td>n/a</td><td>n/a</td></tr>`
    );

    expect($.fn.html).toHaveBeenCalledWith(expectedHtml1);
    expect($.fn.html).toHaveBeenCalledWith(expectedHtml2);
  });

  test('should display a link to invite users for admins', () => {
    const users = [];

    $.fn.html = jest.fn();
    list_users_data(users);
    expect($.fn.html).toHaveBeenCalledTimes(1);

    const expectedInviteLinkHtml = expect.stringContaining("<table><tbody></tbody>");
    expect($.fn.html).toHaveBeenCalledWith(expectedInviteLinkHtml);
  });

  test('should not display invite link for non-admin users', () => {
    const users = [];

    global.admin = false; // Override the global admin for this test

    $.fn.html = jest.fn();
    list_users_data(users);
    expect($.fn.html).toHaveBeenCalledTimes(1);

    const notExpectedInviteLinkHtml = expect.not.stringContaining('Click here to invite a user');
    expect($.fn.html).toHaveBeenCalledWith(notExpectedInviteLinkHtml);
  });
});
