/**
 * @jest-environment jsdom
 */

const $ = require('jquery');
global.$ = $;

const module  = require('../static/planttracer.js') 
const list_users_data = module.list_users_data

global.Audio = function() {
  this.play = jest.fn();
};



describe('list_users_data', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('should create the correct HTML for active users', () => {
    const users = [
      {
        user_id: 1,
        name: 'User 1',
        email: 'user1@example.com',
        active: true,
        date_joined: 1627689600,
        last_login: 1627789600,
      },
    ];

    global.admin = true;
    global.user_id = 1;
    global.user_demo = 'false';
    global.TABLE_HEAD = '<tr><th>ID</th><th>Name</th><th>Email</th><th>Date Joined</th><th>Last Login</th><th>Status</th><th>Actions</th></tr>';
    global.user_id = 1;
    global.user_demo = false;
    global.PLAY_LABEL = 'Play';
    global.PLAY_TRACKED_LABEL = 'Play Tracked';
    global.UNPUBLISH_BUTTON = 'Unpublish';
    global.PUBLISH_BUTTON = 'Publish';
    global.DELETE_BUTTON = 'Delete';
    global.UNDELETE_BUTTON = 'Undelete';
    global.user_primary_course_id = 2;

    $.fn.html = jest.fn();
    list_users_data(users);
    expect($.fn.html).toHaveBeenCalledTimes(1);

    const expectedHtml = expect.stringContaining("<table><tbody><tr><td>User 1 (1) </td><td>user1@example.com</td><td>n/a</td><td>n/a</td></tr>");
    expect($.fn.html).toHaveBeenCalledWith(expectedHtml);
  });


  test('should correctly classify and display inactive users', () => {
    const users = [
      {
        user_id: 1,
        name: 'User 1',
        email: 'user1@example.com',
        active: false,
        date_joined: 1627689600,
        last_login: 1627789600,
      },
      {
        user_id: 2,
        name: 'User 2',
        email: 'user2@example.com',
        active: true,
        date_joined: 1627689600,
        last_login: 1627789600,
      },
    ];

    global.admin = true;
    global.user_id = 1;
    global.TABLE_HEAD = '<tr><th>ID</th><th>Name</th><th>Email</th><th>Date Joined</th><th>Last Login</th><th>Status</th><th>Actions</th></tr>';

    $.fn.html = jest.fn();
    list_users_data(users);
    expect($.fn.html).toHaveBeenCalledTimes(1);

    const expectedHtml = expect.stringContaining('<table><tbody><tr><td>User 1 (1) </td><td>user1@example.com</td><td>n/a</td><td>n/a</td></tr>');
    const expectedHtml2 = expect.stringContaining('<tr><td>User 2 (2) </td><td>user2@example.com</td><td>n/a</td><td>n/a</td></tr>');
    expect($.fn.html).toHaveBeenCalledWith(expectedHtml);
    expect($.fn.html).toHaveBeenCalledWith(expectedHtml2);
  });

  test('should display a link to invite users for admins', () => {
    const users = [];

    global.admin = true;
    global.user_id = 1;
    global.TABLE_HEAD = '<tr><th>ID</th><th>Name</th><th>Email</th><th>Date Joined</th><th>Last Login</th><th>Status</th><th>Actions</th></tr>';

    $.fn.html = jest.fn();
    list_users_data(users);
    expect($.fn.html).toHaveBeenCalledTimes(1);

    const expectedInviteLinkHtml = expect.stringContaining("<table><tbody></tbody>");
    expect($.fn.html).toHaveBeenCalledWith(expectedInviteLinkHtml);
  });

  test('should not display invite link for non-admin users', () => {
    const users = [];

    global.admin = false;
    global.user_id = 1;
    global.TABLE_HEAD = '<tr><th>ID</th><th>Name</th><th>Email</th><th>Date Joined</th><th>Last Login</th><th>Status</th><th>Actions</th></tr>';

    $.fn.html = jest.fn();
    list_users_data(users);
    expect($.fn.html).toHaveBeenCalledTimes(1);

    const notExpectedInviteLinkHtml = expect.not.stringContaining('Click here to invite a user');
    expect($.fn.html).toHaveBeenCalledWith(notExpectedInviteLinkHtml);
  });
});
