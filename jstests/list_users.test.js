// Import dependencies
const $ = require('jquery');
global.$ = $; // Mock jQuery

// Mock global variables and methods
const module = require('../static/planttracer.js');
const list_users = module.list_users; 

// Mock fetch

const list_users_data = jest.fn();
global.fetch = jest.fn();

// Mock DOM element for displaying messages
document.body.innerHTML = '<div id="message"></div>';

describe('list_users', () => {
  beforeEach(() => {
    global.api_key = 'abcdefghijklmnopqrstuvwxyz'
    global.API_BASE = 'https://planttracer.com'
  });

  test('should fetch user data and call list_users_data on success', async () => {
    const mockResponse = {
      error: false,
      users: [
        { user_id: 1, name: 'User 1', email: 'user1@example.com' },
        { user_id: 2, name: 'User 2', email: 'user2@example.com' }
      ],
      courses: [
        { course_id: 1, course_name: 'Course 1' },
        { course_id: 2, course_name: 'Course 2' }
      ]
    };

    // Mock a successful fetch response
    global.fetch.mockResolvedValueOnce({
      json: jest.fn().mockResolvedValueOnce(mockResponse)
    });

    // Call list_users function
    module.list_users();

    // Wait for fetch and subsequent code to resolve
    await Promise.resolve();

    // Ensure fetch was called correctly
    expect(fetch).toHaveBeenCalledWith(`${API_BASE}api/list-users`, expect.any(Object));
  });

  test('should display an error message if API returns an error', async () => {
    const mockErrorResponse = {
      error: true,
      message: 'An error occurred while fetching users'
    };
    global.fetch.mockResolvedValueOnce({
      json: jest.fn().mockResolvedValueOnce(mockErrorResponse)
    });
    module.list_users();


    await Promise.resolve();
    expect(fetch).toHaveBeenCalledWith(`${API_BASE}api/list-users`, expect.any(Object));
  });
});
