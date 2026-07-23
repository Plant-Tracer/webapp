const {
  appendCourseRows,
  appendMovieRows,
  appendUserRows,
  loadAdminSummary,
  state,
} = require('admin');

function adminDocument() {
  document.body.innerHTML = `
    <p id="admin-status"></p>
    <span id="admin-course-count"></span>
    <span id="admin-user-count"></span>
    <span id="admin-movie-count"></span>
    <table><tbody id="admin-course-rows"></tbody></table>
    <table><tbody id="admin-user-rows"></tbody></table>
    <table><tbody id="admin-movie-rows"></tbody></table>
    <button id="admin-more-courses"></button>
    <button id="admin-more-users"></button>
    <button id="admin-more-movies"></button>`;
}

function payload() {
  return {
    viewer: { user_name: 'Root Reader' },
    counts: { courses: 1, users: 1, movies: 1 },
    courses: {
      items: [{
        course_id: 'BIO-1', course_name: 'Biology', admin_count: 1,
        enrollment_count: 7, max_enrollment: 10,
      }],
      restart_marker: null,
    },
    users: {
      items: [{
        user_name: 'Ada', email: 'ada@example.test', primary_course_id: 'BIO-1',
        super_role: 'none',
        courses: [
          { course_id: 'BIO-1', course_name: 'Biology', is_admin: true },
          { course_id: 'CHEM-2', course_name: 'Chemistry', is_admin: false },
        ],
      }],
      restart_marker: null,
    },
    movies: {
      items: [{
        title: 'Bean Growth', course_name: 'Biology', owner_name: 'Ada',
        state: 'published', status: 'ready',
      }],
      restart_marker: null,
    },
  };
}

describe('admin summary rendering', () => {
  beforeEach(() => {
    adminDocument();
    global.API_BASE = '/';
    fetch.resetMocks();
    state.courseMarker = null;
    state.userMarker = null;
    state.movieMarker = null;
  });

  test('renders enrollment, named memberships, and movies', async () => {
    fetch.mockResponseOnce(JSON.stringify(payload()));

    await loadAdminSummary();

    expect(document.getElementById('admin-course-rows').textContent).toContain('7 / 10');
    const userRow = document.getElementById('admin-user-rows');
    expect(userRow.textContent).toContain('Biology, Chemistry');
    expect(userRow.querySelector('strong').textContent).toBe('Biology');
    expect(document.getElementById('admin-movie-rows').textContent)
      .toContain('Bean GrowthBiologyAdapublishedready');
  });

  test('uses the movie restart marker when loading more movies', async () => {
    const nextPayload = payload();
    nextPayload.movies.items[0].title = 'Second Movie';
    state.movieMarker = 'movie-token';
    fetch.mockResponseOnce(JSON.stringify(nextPayload));

    await loadAdminSummary({ appendMovies: true });

    expect(fetch.mock.calls[0][0]).toContain('movie_marker=movie-token');
    expect(document.getElementById('admin-movie-rows').textContent).toContain('Second Movie');
  });

  test('row helpers render supplied data without HTML interpretation', () => {
    appendCourseRows(payload().courses.items);
    appendUserRows(payload().users.items);
    appendMovieRows([{ ...payload().movies.items[0], title: '<script>bad()</script>' }]);

    expect(document.querySelector('#admin-movie-rows script')).toBeNull();
    expect(document.getElementById('admin-movie-rows').textContent).toContain('<script>bad()</script>');
  });
});
