/**
 * @jest-environment jsdom
 */

const $ = require('jquery');
const fs = require('fs');
const path = require('path');
global.$ = $;

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

    $.fn.html = jest.fn();
    list_movies_data(movies);
    expect($.fn.html).toHaveBeenCalledTimes(4);

    const expectedPublishedHtml = expect.stringContaining("<table><tbody><tr><td><i>");
    expect($.fn.html).toHaveBeenCalledWith(expectedPublishedHtml);
  });

  test('should handle an empty list of movies gracefully', () => {
    const movies = [];

    $.fn.html = jest.fn();
    list_movies_data(movies);
    expect($.fn.html).toHaveBeenCalledTimes(4);

      // Simson broke this with the dynamodb update. It needs to be fixed.
      //const expectedEmptyHtml = expect.stringContaining('<table><tbody><tr><td><i>No movies</i></td></tr></tbody></table>');
      const expectedEmptyHtml = expect.stringContaining("<table><tbody><tr><td><i>No movies</i></td></tr><tr><td colspan=\"6\"><a href=\"/upload\">Click here to upload a movie</a></td></tr></tbody></table>");
    expect($.fn.html).toHaveBeenCalledWith(expectedEmptyHtml);
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

    $.fn.html = jest.fn();
    list_movies_data(movies);
    expect($.fn.html).toHaveBeenCalledTimes(4);

    const expectedCourseHtml = expect.stringContaining('<table>');
    expect($.fn.html).toHaveBeenCalledWith(expectedCourseHtml);
  });

  test('should display a link to upload movies for non-demo users', () => {
    const movies = [];
    global.demo_mode = false;
    $.fn.html = jest.fn();
    list_movies_data(movies);
    expect($.fn.html).toHaveBeenCalledTimes(4);

    const expectedUploadLinkHtml = expect.stringContaining('<table><tbody><tr><td><i>No movies</i></td></tr><tr><td colspan="6"><a href="/upload">Click here to upload a movie</a></td></tr></tbody></table>');
    expect($.fn.html).toHaveBeenCalledWith(expectedUploadLinkHtml);
  });

  test('should not display upload link for demo users', () => {
    const movies = [];

    global.demo_mode = true;

    $.fn.html = jest.fn();
    list_movies_data(movies);
    expect($.fn.html).toHaveBeenCalledTimes(4);

    const notExpectedUploadLinkHtml = expect.not.stringContaining('Click here to upload a movie');
    expect($.fn.html).toHaveBeenCalledWith(notExpectedUploadLinkHtml);
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
      }
    ];

    $.fn.html = jest.fn();
    list_movies_data(movies);

    const expectedButtonHtml = expect.stringContaining(`<td> Status: Not published<br/>`);
    expect($.fn.html).toHaveBeenCalledWith(expectedButtonHtml);
  });

  test('should display an unpublish button for published movies', () => {
    const movies = [
      {
        movie_id: 1,
        user_id: 1,
        published: 1,
        deleted: 0,
        title: 'Published Movie',
      }
    ];

    $.fn.html = jest.fn();
    list_movies_data(movies);

    const expectedButtonHtml = expect.stringContaining(`<td> Status: <b>Published</b>`);
    expect($.fn.html).toHaveBeenCalledWith(expectedButtonHtml);
  });
});
