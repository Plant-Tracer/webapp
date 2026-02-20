/**
 * @jest-environment jsdom
 */

const { $ } = require('utils');
const fs = require('fs');
const path = require('path');

const module = require('planttracer');
const list_movies_data = module.list_movies_data;

global.Audio = function() {
  this.play = jest.fn();
};

// Load global data from globals.json
let globalData;
beforeAll(() => {
  const jsonPath = path.join(__dirname, 'constants.json');
  globalData = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
});

describe('list_movies_data', () => {
  let mockElements;

  beforeEach(() => {
    jest.clearAllMocks();
    // Assign global variables from globalData
    global.user_id = parseInt(globalData.user_id, 10);
    global.admin = globalData.admin === 'true';
    global.demo_mode = globalData.demo_mode === 'false';
    global.PLAY_LABEL = globalData.PLAY_LABEL;
    global.PLAY_TRACKED_LABEL = globalData.PLAY_TRACKED_LABEL;
    global.UNPUBLISH_BUTTON = globalData.UNPUBLISH_BUTTON;
    global.PUBLISH_BUTTON = globalData.PUBLISH_BUTTON;
    global.DELETE_BUTTON = globalData.DELETE_BUTTON;
    global.UNDELETE_BUTTON = globalData.UNDELETE_BUTTON;
    global.TABLE_HEAD = globalData.TABLE_HEAD;
    global.user_primary_course_id = parseInt(globalData.user_primary_course_id, 10);

    // Mock document.querySelector to return mock elements with innerHTML setter
    mockElements = {};
    document.querySelector = jest.fn((selector) => {
      if (!mockElements[selector]) {
        mockElements[selector] = { innerHTML: '', style: {} };
      }
      return mockElements[selector];
    });

    // Mock document.querySelectorAll for hiding movie players
    document.querySelectorAll = jest.fn(() => []);
  });

  test('should create the correct HTML for published movies', () => {
    const movies = [
      {
        movie_id: 1,
        user_id: 1,
        published: 1,
        title: 'Movie Title',
        description: 'Description',
        width: 1280,
        height: 720,
        total_bytes: 2000000,
        fps: '30',
        total_frames: 3600,
        date_uploaded: 1627689600,
        deleted: 0,
        orig_movie: false,
      }
    ];

    list_movies_data(movies);
    expect(document.querySelector).toHaveBeenCalledTimes(4);

    // Check that the published movies div was populated
    const publishedHtml = mockElements['#your-published-movies'].innerHTML;
    expect(publishedHtml).toContain("<table>");
    expect(publishedHtml).toContain("Movie Title");
  });

  test('should handle an empty list of movies gracefully', () => {
    const movies = [];

    list_movies_data(movies);
    expect(document.querySelector).toHaveBeenCalledTimes(4);

    // Check that empty movies show the right message
    const publishedHtml = mockElements['#your-published-movies'].innerHTML;
    expect(publishedHtml).toContain("No movies");
    expect(publishedHtml).toContain('<a href="/upload">Click here to upload a movie</a>');
  });

  test('should correctly classify and display course movies', () => {
    const movies = [
      {
        movie_id: 1,
        user_id: 2,
        course_id: 1,
        published: 0,
        deleted: 0,
        orig_movie: false,
      },
      {
        movie_id: 2,
        user_id: 3,
        course_id: 2,
        published: 0,
        deleted: 0,
        orig_movie: false,
      }
    ];

    list_movies_data(movies);
    expect(document.querySelector).toHaveBeenCalledTimes(4);

    // Check that course movies are shown in the right section
    const courseHtml = mockElements['#course-movies'].innerHTML;
    expect(courseHtml).toContain('<table>');
  });

  test('should display a link to upload movies for non-demo users', () => {
    const movies = [];
    global.demo_mode = false;
    list_movies_data(movies);
    expect(document.querySelector).toHaveBeenCalledTimes(4);

    const publishedHtml = mockElements['#your-published-movies'].innerHTML;
    expect(publishedHtml).toContain('No movies');
    expect(publishedHtml).toContain('<a href="/upload">Click here to upload a movie</a>');
  });

  test('should not display upload link for demo users', () => {
    const movies = [];

    global.demo_mode = true;

    list_movies_data(movies);
    expect(document.querySelector).toHaveBeenCalledTimes(4);

    const publishedHtml = mockElements['#your-published-movies'].innerHTML;
    expect(publishedHtml).not.toContain('Click here to upload a movie');
  });

  // Action Button Tests

  test('should display a publish button for unpublished movies (admin)', () => {
    global.admin = true; // Set admin privileges

    const movies = [
      {
        movie_id: 1,
        user_id: 1,
        published: 0,
        deleted: 0,
        title: 'Unpublished Movie',
        date_uploaded: 1627689600,
        width: 1280,
        height: 720,
        total_bytes: 2000000,
        fps: '30',
        total_frames: 3600,
        orig_movie: false,
      }
    ];

    list_movies_data(movies);

    const unpublishedHtml = mockElements['#your-unpublished-movies'].innerHTML;
    expect(unpublishedHtml).toContain('Status: Not published');
  });

  test('should display an unpublish button for published movies', () => {
    const movies = [
      {
        movie_id: 1,
        user_id: 1,
        published: 1,
        deleted: 0,
        title: 'Published Movie',
        date_uploaded: 1627689600,
        width: 1280,
        height: 720,
        total_bytes: 2000000,
        fps: '30',
        total_frames: 3600,
        orig_movie: false,
      }
    ];

    list_movies_data(movies);

    const publishedHtml = mockElements['#your-published-movies'].innerHTML;
    expect(publishedHtml).toContain('Status: <b>Published</b>');
  });
});
