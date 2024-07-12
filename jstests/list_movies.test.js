/**
 * @jest-environment jsdom
 */


const $ = require('jquery');
global.$ = $;

const list_movies_data = require('../static/planttracer')

global.Audio = function() {
  this.play = jest.fn();
};


  describe('list_movies_data', () => {
    beforeEach(() => {
      jest.clearAllMocks();
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
          fps: 30,
          total_frames: 3600,
          date_uploaded: 1627689600,
          deleted: 0,
          orig_movie: false,
        }
      ];
  
      global.user_id = 1;
      global.admin = true;
      global.user_demo = false;
      global.PLAY_LABEL = 'Play';
      global.PLAY_TRACKED_LABEL = 'Play Tracked';
      global.UNPUBLISH_BUTTON = 'Unpublish';
      global.PUBLISH_BUTTON = 'Publish';
      global.DELETE_BUTTON = 'Delete';
      global.UNDELETE_BUTTON = 'Undelete';
      global.TABLE_HEAD = '<tr><th>ID</th><th>Name</th><th>Date</th><th>Title</th><th>Description</th><th>Stats</th><th>Actions</th></tr>';
      global.user_primary_course_id = 2;
  

      $.fn.html = jest.fn();
      list_movies_data(movies);
      expect($.fn.html).toHaveBeenCalledTimes(4);
  
      const expectedPublishedHtml = expect.stringContaining('<table>');
      expect($.fn.html).toHaveBeenCalledWith(expectedPublishedHtml);
    });
  
    test('should handle an empty list of movies gracefully', () => {
      const movies = [];
  
      global.user_id = 1;
      global.admin = true;
      global.user_demo = false;
      global.PLAY_LABEL = 'Play';
      global.PLAY_TRACKED_LABEL = 'Play Tracked';
      global.UNPUBLISH_BUTTON = 'Unpublish';
      global.PUBLISH_BUTTON = 'Publish';
      global.DELETE_BUTTON = 'Delete';
      global.UNDELETE_BUTTON = 'Undelete';
      global.TABLE_HEAD = '<tr><th>ID</th><th>Name</th><th>Date</th><th>Title</th><th>Description</th><th>Stats</th><th>Actions</th></tr>';
      global.user_primary_course_id = 2;
  
      $.fn.html = jest.fn();
      list_movies_data(movies);
      expect($.fn.html).toHaveBeenCalledTimes(4);
  
      const expectedEmptyHtml = expect.stringContaining('<i>No movies</i>');
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
  

      global.user_id = 1;
      global.admin = true;
      global.user_demo = false;
      global.PLAY_LABEL = 'Play';
      global.PLAY_TRACKED_LABEL = 'Play Tracked';
      global.UNPUBLISH_BUTTON = 'Unpublish';
      global.PUBLISH_BUTTON = 'Publish';
      global.DELETE_BUTTON = 'Delete';
      global.UNDELETE_BUTTON = 'Undelete';
      global.TABLE_HEAD = '<tr><th>ID</th><th>Name</th><th>Date</th><th>Title</th><th>Description</th><th>Stats</th><th>Actions</th></tr>';
      global.user_primary_course_id = 2;
  

      $.fn.html = jest.fn();
      list_movies_data(movies);
      expect($.fn.html).toHaveBeenCalledTimes(4);
  

      const expectedCourseHtml = expect.stringContaining('<table>');
      expect($.fn.html).toHaveBeenCalledWith(expectedCourseHtml);
    });
  
    test('should display a link to upload movies for non-demo users', () => {
      const movies = [];
  

      global.user_id = 1;
      global.admin = true;
      global.user_demo = false;
      global.PLAY_LABEL = 'Play';
      global.PLAY_TRACKED_LABEL = 'Play Tracked';
      global.UNPUBLISH_BUTTON = 'Unpublish';
      global.PUBLISH_BUTTON = 'Publish';
      global.DELETE_BUTTON = 'Delete';
      global.UNDELETE_BUTTON = 'Undelete';
      global.TABLE_HEAD = '<tr><th>ID</th><th>Name</th><th>Date</th><th>Title</th><th>Description</th><th>Stats</th><th>Actions</th></tr>';
      global.user_primary_course_id = 2;

      $.fn.html = jest.fn();
      list_movies_data(movies);
      expect($.fn.html).toHaveBeenCalledTimes(4);

      const expectedUploadLinkHtml = expect.stringContaining('Click here to upload a movie');
      expect($.fn.html).toHaveBeenCalledWith(expectedUploadLinkHtml);
    });
  
    test('should not display upload link for demo users', () => {
      const movies = [];
  

      global.user_id = 1;
      global.admin = true;
      global.user_demo = true;
      global.PLAY_LABEL = 'Play';
      global.PLAY_TRACKED_LABEL = 'Play Tracked';
      global.UNPUBLISH_BUTTON = 'Unpublish';
      global.PUBLISH_BUTTON = 'Publish';
      global.DELETE_BUTTON = 'Delete';
      global.UNDELETE_BUTTON = 'Undelete';
      global.TABLE_HEAD = '<tr><th>ID</th><th>Name</th><th>Date</th><th>Title</th><th>Description</th><th>Stats</th><th>Actions</th></tr>';
      global.user_primary_course_id = 2;

      $.fn.html = jest.fn();
      list_movies_data(movies);
      expect($.fn.html).toHaveBeenCalledTimes(4);
  
      const notExpectedUploadLinkHtml = expect.not.stringContaining('Click here to upload a movie');
      expect($.fn.html).toHaveBeenCalledWith(notExpectedUploadLinkHtml);
    });
  });