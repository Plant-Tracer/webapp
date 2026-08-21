const {
  loadAdminSummary,
  populateExistingCourseAdmins,
  syncCourseAdminName,
  state,
} = require('admin');

function adminDocument() {
  document.body.innerHTML = `
    <p id="admin-status"></p>
    <span id="admin-course-count"></span>
    <span id="admin-user-count"></span>
    <span id="admin-movie-count"></span>
    <label><input id="admin-verbose-details" type="checkbox"></label>
    <button id="admin-new-course" type="button" hidden>New course</button>
    <dialog id="admin-course-dialog">
      <form id="admin-course-form">
        <input id="admin-course-name" name="course_name">
        <input id="admin-course-id" name="course_id">
        <input id="admin-course-admin-email" name="admin_email" list="admin-existing-course-admins">
        <datalist id="admin-existing-course-admins"></datalist>
        <input id="admin-course-admin-name" name="admin_name">
        <p id="admin-course-form-status"></p>
        <button id="admin-course-cancel" type="button">Cancel</button>
        <button id="admin-course-submit" type="submit">Create course</button>
      </form>
    </dialog>
    <table data-resizable-table>
      <thead><tr>
        <th><button class="admin-sort" data-table="courses" data-key="course_name">
          Name <span class="admin-sort-indicator"></span>
        </button></th>
      </tr></thead>
      <tbody id="admin-course-rows"></tbody>
    </table>
    <table data-resizable-table>
      <thead><tr>
        <th><button class="admin-sort" data-table="users" data-key="user_name">
          Name <span class="admin-sort-indicator"></span>
        </button></th>
      </tr></thead>
      <tbody id="admin-user-rows"></tbody>
    </table>
    <table data-resizable-table>
      <thead><tr>
        <th><button class="admin-sort" data-table="movies" data-key="title">
          Title <span class="admin-sort-indicator"></span>
        </button></th>
      </tr></thead>
      <tbody id="admin-movie-rows"></tbody>
    </table>
    <dialog id="course-admin-dialog">
      <div><h2 id="course-admin-dialog-title"></h2>
        <button id="course-admin-dialog-close" type="button">×</button></div>
      <p id="course-admin-dialog-status"></p>
      <ul id="course-admin-current"></ul>
      <select id="course-admin-user-select"></select>
      <button id="course-admin-add" type="button">Add administrator</button>
    </dialog>`;
}

function payload() {
  return {
    viewer: { user_name: 'Root Reader', super_role: 'superauditor' },
    counts: { courses: 2, users: 1, movies: 1 },
    courses: {
      items: [
        {
          course_id: 'BIO-1', course_key: 'grow-beans', course_name: 'Biology', admin_count: 1,
          enrollment_count: 7, max_enrollment: 10, created_at: 1700000000,
          last_movie_activity_at: null,
        },
        {
          course_id: 'CHEM-2', course_key: 'grow-salts', course_name: 'Chemistry', admin_count: 1,
          enrollment_count: 4, max_enrollment: 10, created_at: null,
          last_movie_activity_at: null,
        },
      ],
      restart_marker: null,
    },
    users: {
      items: [{
        user_id: 'user-1', user_name: 'Ada', email: 'ada@example.test', default_course_id: 'BIO-1',
        enabled: true, super_role: 'none', created_at: 1700000000, last_movie_activity_at: null,
        courses: [
          { course_id: 'BIO-1', is_admin: true },
          { course_id: 'CHEM-2', is_admin: false },
        ],
      }],
      restart_marker: null,
    },
    movies: {
      items: [{
        movie_id: 'movie-1', title: 'Bean Growth', course_id: 'BIO-1', user_id: 'user-1',
        owner_name: 'Ada', state: 'published', status: 'ready', created_at: 1700000000,
        uploaded_at: 1700000100, last_activity_at: 1700000200, total_frames: 121,
        total_bytes: 2500000, fpm: '60', has_traced_movie: true,
        description: 'Daily bean measurement', fps: '30', width: 640, height: 480,
        rotation: 0, trim_start_frame: 0, trim_end_frame: 120, needs_retracing: false,
        research_use: 1, credit_by_name: 'Ada', attribution_name: 'Ada Lovelace',
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
    state.courses = [];
    state.users = [];
    state.movies = [];
    state.viewerRole = 'none';
    state.sort.courses = { key: 'course_name', direction: 1 };
    state.sort.users = { key: 'user_name', direction: 1 };
    state.sort.movies = { key: 'title', direction: 1 };
    HTMLDialogElement.prototype.showModal = jest.fn(function showModal() {
      this.open = true;
    });
    HTMLDialogElement.prototype.close = jest.fn(function close() {
      this.open = false;
    });
  });

  test('renders enrollment, named memberships, and movies', async () => {
    fetch.mockResponseOnce(JSON.stringify(payload()));

    await loadAdminSummary();

    const key = document.querySelector('.admin-course-key');
    const keyToggle = document.querySelector('.admin-key-toggle');
    expect(key.textContent).toBe('••••••••');
    expect(document.getElementById('admin-course-rows').textContent).not.toContain('grow-beans');
    expect(keyToggle.querySelector('.admin-eye-slash')).not.toBeNull();
    keyToggle.click();
    expect(key.textContent).toBe('grow-beans');
    expect(keyToggle.querySelector('.admin-eye-slash')).toBeNull();
    expect(keyToggle.getAttribute('aria-label')).toBe('Hide course key for Biology');
    keyToggle.click();
    expect(key.textContent).toBe('••••••••');
    expect(keyToggle.querySelector('.admin-eye-slash')).not.toBeNull();
    expect(document.getElementById('admin-course-rows').textContent).toContain('7 / 10');
    expect(document.getElementById('admin-course-rows').textContent).toContain('Ada (ada@example.test)');
    expect(document.querySelector('.course-admin-manage')).toBeNull();
    const userRow = document.getElementById('admin-user-rows');
    expect(userRow.textContent).toContain('Biology, Chemistry');
    expect(userRow.querySelector('strong').textContent).toBe('Biology');
    const movieRow = document.querySelector('#admin-movie-rows tr');
    expect(movieRow.textContent).toContain('Bean Growth');
    expect(movieRow.textContent).toContain('121 frames · 2 min elapsed · 2.5 MB');
    expect(movieRow.querySelector('.admin-actions-toggle').textContent).toBe('⋮');
    expect(movieRow.querySelector('.admin-actions-menu').textContent).toContain('Play');
    expect(movieRow.querySelector('.admin-actions-menu').textContent).toContain('Download traced');
    expect(movieRow.querySelector('.admin-actions-menu').textContent).not.toContain('Analyze');
    expect(document.querySelectorAll('.admin-resize-handle')).toHaveLength(3);
    expect(document.getElementById('admin-new-course').hidden).toBe(true);
    const courseLink = document.querySelector('#admin-course-rows a');
    expect(courseLink.href).toContain('/list?course_id=BIO-1');
    expect(courseLink.target).toBe('_blank');
  });

  test('loads every table page and globally sorts movies', async () => {
    const initial = payload();
    initial.courses.items[0].course_name = 'Zoology';
    initial.courses.restart_marker = 'course-token';
    initial.users.items[0].user_name = 'Zoe';
    initial.users.restart_marker = 'user-token';
    initial.movies.items[0].title = 'Zinnia Growth';
    initial.movies.restart_marker = 'movie-token';
    const nextItems = {
      courses: {
        ...payload(),
        courses: {
          items: [{ ...payload().courses.items[0], course_id: 'BIO-2' }],
          restart_marker: null,
        },
      },
      users: {
        ...payload(),
        users: {
          items: [{ ...payload().users.items[0], user_id: 'user-2' }],
          restart_marker: null,
        },
      },
      movies: {
        ...payload(),
        movies: {
          items: [{ ...payload().movies.items[0], movie_id: 'movie-2' }],
          restart_marker: null,
        },
      },
    };
    fetch.mockImplementation(async (url) => {
      const section = new URL(url, 'https://example.test').searchParams.get('section');
      return {
        ok: true,
        status: 200,
        json: async () => (section === 'all' ? initial : nextItems[section]),
      };
    });

    await loadAdminSummary();

    expect(fetch.mock.calls.map((call) => call[0])).toEqual(expect.arrayContaining([
      expect.stringContaining('section=courses&course_marker=course-token'),
      expect.stringContaining('section=users&user_marker=user-token'),
      expect.stringContaining('section=movies&movie_marker=movie-token'),
    ]));
    expect(document.querySelector('#admin-course-rows tr').textContent).toContain('Biology');
    expect(document.querySelector('#admin-user-rows tr').textContent).toContain('Ada');
    expect(document.querySelector('#admin-movie-rows tr').textContent).toContain('Bean Growth');
    document.querySelector('[data-table="movies"]').click();
    expect(document.querySelector('#admin-movie-rows tr').textContent).toContain('Zinnia Growth');
    expect(document.querySelector('[data-table="movies"]').closest('th').getAttribute('aria-sort'))
      .toBe('descending');
  });

  test('renders supplied data without HTML interpretation', async () => {
    const untrusted = payload();
    untrusted.movies.items[0].title = '<script>bad()</script>';
    fetch.mockResponseOnce(JSON.stringify(untrusted));

    await loadAdminSummary();

    expect(document.querySelector('#admin-movie-rows script')).toBeNull();
    expect(document.getElementById('admin-movie-rows').textContent).toContain('<script>bad()</script>');
  });

  test('marks pending uploads red and suppresses unusable actions', async () => {
    const adminPayload = payload();
    adminPayload.viewer.super_role = 'superadmin';
    adminPayload.movies.items[0].uploaded_at = null;
    fetch.mockResponseOnce(JSON.stringify(adminPayload));

    await loadAdminSummary();

    const movieRow = document.querySelector('#admin-movie-rows tr');
    expect(movieRow.classList.contains('admin-upload-pending')).toBe(true);
    expect(movieRow.title).toContain('upload has not completed');
    expect(movieRow.firstElementChild.querySelector('a')).toBeNull();
    expect(movieRow.querySelector('.admin-actions-menu')).toBeNull();
    expect(movieRow.lastElementChild.textContent).toBe('—');
  });

  test('links uploaded movies to Analyze for superadmins', async () => {
    const adminPayload = payload();
    adminPayload.viewer.super_role = 'superadmin';
    fetch.mockResponseOnce(JSON.stringify(adminPayload));

    await loadAdminSummary();

    const movieRow = document.querySelector('#admin-movie-rows tr');
    expect(movieRow.querySelector('td a').href).toContain('/analyze?movie_id=movie-1');
    expect(movieRow.querySelector('.admin-actions-menu').textContent).toContain('Analyze');
  });

  test('shows course creation only to superadmins and offers only existing admins', async () => {
    const adminPayload = payload();
    adminPayload.viewer.super_role = 'superadmin';
    adminPayload.users.items.push({
      user_id: 'user-2', user_name: 'Grace', email: 'grace@example.test',
      enabled: true, default_course_id: 'BIO-1', super_role: 'none', created_at: 1700000001,
      last_movie_activity_at: null, courses: [{ course_id: 'BIO-1', is_admin: false }],
    });
    adminPayload.users.items.push({
      user_id: 'user-3', user_name: 'Disabled Admin', email: 'disabled@example.test',
      enabled: false, default_course_id: 'BIO-1', super_role: 'none', created_at: 1700000002,
      last_movie_activity_at: null, courses: [{ course_id: 'BIO-1', is_admin: true }],
    });
    adminPayload.users.items.push({
      user_id: 'user-4', user_name: ' ', email: 'nameless@example.test',
      enabled: true, default_course_id: 'BIO-1', super_role: 'none', created_at: 1700000003,
      last_movie_activity_at: null, courses: [{ course_id: 'BIO-1', is_admin: true }],
    });
    fetch.mockResponseOnce(JSON.stringify(adminPayload));

    await loadAdminSummary();
    populateExistingCourseAdmins();

    expect(document.getElementById('admin-new-course').hidden).toBe(false);
    const options = [...document.querySelectorAll('#admin-existing-course-admins option')];
    expect(options.map((option) => option.value)).toEqual(['ada@example.test']);
    const email = document.getElementById('admin-course-admin-email');
    const name = document.getElementById('admin-course-admin-name');
    email.value = 'ADA@example.test';
    syncCourseAdminName();
    expect(name.value).toBe('Ada');
    expect(name.readOnly).toBe(true);
    email.value = 'grace@example.test';
    syncCourseAdminName();
    expect(name.value).toBe('Grace');
    expect(name.readOnly).toBe(true);
    email.value = 'new@example.test';
    syncCourseAdminName();
    expect(name.value).toBe('');
    expect(name.readOnly).toBe(false);
  });

  test('submits a new course and refreshes the admin summary', async () => {
    const adminPayload = payload();
    adminPayload.viewer.super_role = 'superadmin';
    fetch.mockResponseOnce(JSON.stringify(adminPayload));
    const dialog = document.getElementById('admin-course-dialog');
    dialog.showModal = jest.fn();
    dialog.close = jest.fn();

    await loadAdminSummary();
    document.getElementById('admin-new-course').click();
    expect(dialog.showModal).toHaveBeenCalledTimes(1);
    document.getElementById('admin-course-name').value = 'Botany';
    document.getElementById('admin-course-id').value = 'BOT-3';
    document.getElementById('admin-course-admin-email').value = 'new@example.test';
    document.getElementById('admin-course-admin-name').value = 'New Administrator';
    fetch.mockResponseOnce(JSON.stringify({
      error: false, email_sent: true, message: 'Course created and administrator email sent',
    }), { status: 201 });
    fetch.mockResponseOnce(JSON.stringify(adminPayload));

    document.getElementById('admin-course-form').dispatchEvent(new Event('submit', {
      bubbles: true,
      cancelable: true,
    }));
    await new Promise((resolve) => { setTimeout(resolve, 0); });
    await new Promise((resolve) => { setTimeout(resolve, 0); });

    const request = fetch.mock.calls[1];
    expect(request[0]).toBe('/api/admin/courses');
    expect(request[1].method).toBe('POST');
    expect(JSON.parse(request[1].body)).toEqual({
      course_name: 'Botany',
      course_id: 'BOT-3',
      admin_email: 'new@example.test',
      admin_name: 'New Administrator',
    });
    expect(dialog.close).toHaveBeenCalledTimes(1);
    expect(document.getElementById('admin-status').textContent)
      .toBe('Course created and administrator email sent');
    expect(document.getElementById('admin-status').className).toBe('admin-success');
  });

  test('keeps the course dialog open when creation fails', async () => {
    const adminPayload = payload();
    adminPayload.viewer.super_role = 'superadmin';
    fetch.mockResponseOnce(JSON.stringify(adminPayload));
    const dialog = document.getElementById('admin-course-dialog');
    dialog.showModal = jest.fn();
    dialog.close = jest.fn();

    await loadAdminSummary();
    document.getElementById('admin-course-name').value = 'Conflicting course';
    document.getElementById('admin-course-id').value = 'BIO-1';
    document.getElementById('admin-course-admin-email').value = 'ada@example.test';
    document.getElementById('admin-course-admin-name').value = 'Ada';
    fetch.mockResponseOnce(JSON.stringify({
      error: true,
      message: 'Course ID conflicts with an existing course name',
    }), { status: 409 });

    document.getElementById('admin-course-form').dispatchEvent(new Event('submit', {
      bubbles: true,
      cancelable: true,
    }));
    await new Promise((resolve) => { setTimeout(resolve, 0); });

    expect(dialog.close).not.toHaveBeenCalled();
    expect(document.getElementById('admin-course-form-status').textContent)
      .toBe('Course ID conflicts with an existing course name');
    expect(document.getElementById('admin-course-form-status').className).toBe('admin-error');
    expect(document.getElementById('admin-course-submit').disabled).toBe(false);

    document.getElementById('admin-new-course').click();
    expect(document.getElementById('admin-course-form-status').textContent).toBe('');
    expect(document.getElementById('admin-course-form-status').className).toBe('');
  });

  test('reports a refresh failure visibly after creating a course', async () => {
    const adminPayload = payload();
    adminPayload.viewer.super_role = 'superadmin';
    fetch.mockResponseOnce(JSON.stringify(adminPayload));
    const dialog = document.getElementById('admin-course-dialog');
    dialog.showModal = jest.fn();
    dialog.close = jest.fn();

    await loadAdminSummary();
    document.getElementById('admin-course-admin-email').value = 'new@example.test';
    fetch.mockResponseOnce(JSON.stringify({
      error: false, email_sent: true, message: 'Course created and administrator email sent',
    }), { status: 201 });
    fetch.mockRejectOnce(new Error('network unavailable'));

    document.getElementById('admin-course-form').dispatchEvent(new Event('submit', {
      bubbles: true,
      cancelable: true,
    }));
    await new Promise((resolve) => { setTimeout(resolve, 0); });
    await new Promise((resolve) => { setTimeout(resolve, 0); });

    expect(dialog.close).toHaveBeenCalledTimes(1);
    expect(document.getElementById('admin-status').className).toBe('admin-warning');
    expect(document.getElementById('admin-status').textContent)
      .toBe('Course created and administrator email sent. Admin list refresh failed: network unavailable');
    expect(document.getElementById('admin-course-form-status').className).toBe('');
  });

  test('superadmin manages explicit course administrators', async () => {
    const adminPayload = payload();
    adminPayload.viewer.super_role = 'superadmin';
    adminPayload.users.items.push({
      user_id: 'user-2', user_name: 'Bob', email: 'bob@example.test', enabled: true,
      default_course_id: 'CHEM-2', super_role: 'none', created_at: 1700000001,
      last_movie_activity_at: null, courses: [{ course_id: 'CHEM-2', is_admin: false }],
    });
    fetch
      .mockResponseOnce(JSON.stringify(adminPayload))
      .mockResponseOnce(JSON.stringify({
        error: false, course_id: 'BIO-1', assigned: true, changed: true,
        administrator: { user_id: 'user-2', user_name: 'Bob', email: 'bob@example.test' },
      }));

    await loadAdminSummary();
    document.querySelector('.course-admin-manage').click();

    expect(document.getElementById('course-admin-dialog').open).toBe(true);
    expect(document.getElementById('course-admin-dialog-title').textContent)
      .toBe('Administrators for Biology');
    expect(document.querySelector('#course-admin-current button').disabled).toBe(true);
    expect(document.getElementById('course-admin-user-select').textContent)
      .toContain('Bob (bob@example.test)');

    document.getElementById('course-admin-add').click();
    await new Promise((resolve) => { setTimeout(resolve, 0); });

    expect(fetch.mock.calls[1][0]).toContain('/api/admin/courses/BIO-1/administrators/user-2');
    expect(fetch.mock.calls[1][1].method).toBe('PUT');
    expect(document.getElementById('course-admin-dialog-status').textContent)
      .toBe('Bob (bob@example.test) added.');
    expect(document.getElementById('course-admin-current').textContent).toContain('Bob');
    expect(document.getElementById('admin-course-rows').textContent).toContain('Bob');
    expect(document.querySelector('#course-admin-current button').disabled).toBe(false);
  });

  test('confirms removals and keeps API errors visible in the dialog', async () => {
    const adminPayload = payload();
    adminPayload.viewer.super_role = 'superadmin';
    adminPayload.users.items.push({
      user_id: 'user-2', user_name: 'Bob', email: 'bob@example.test', enabled: true,
      default_course_id: 'BIO-1', super_role: 'none', created_at: 1700000001,
      last_movie_activity_at: null, courses: [{ course_id: 'BIO-1', is_admin: true }],
    });
    fetch
      .mockResponseOnce(JSON.stringify(adminPayload))
      .mockResponseOnce(JSON.stringify({
        error: true, message: 'Administrator assignments changed concurrently; retry the request',
      }), { status: 409 });
    window.confirm = jest.fn(() => true);

    await loadAdminSummary();
    document.querySelector('.course-admin-manage').click();
    document.querySelector('#course-admin-current button').click();
    await new Promise((resolve) => { setTimeout(resolve, 0); });

    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('remain enrolled'));
    expect(fetch.mock.calls[1][1].method).toBe('DELETE');
    const status = document.getElementById('course-admin-dialog-status');
    expect(status.className).toBe('admin-error');
    expect(status.textContent).toContain('changed concurrently');
  });

  test('keeps IDs and operational metadata hidden until verbose details is selected', async () => {
    fetch.mockResponseOnce(JSON.stringify(payload()));

    await loadAdminSummary();

    expect(document.body.textContent).not.toContain('Movie ID: movie-1');
    fetch.mockResponseOnce(JSON.stringify({
      error: false, movie_id: 'movie-1', original_object_state: 'present',
      traced_object_state: 'missing', zip_object_state: 'not created', pending_upload_age_seconds: null,
    }));
    document.getElementById('admin-verbose-details').click();
    await new Promise((resolve) => { setTimeout(resolve, 0); });
    expect(document.body.textContent).toContain('Movie ID: movie-1');
    expect(document.body.textContent).toContain('Description: Daily bean measurement');
    expect(document.body.textContent).toContain('Original object: present');
    expect(document.body.textContent).toContain('Traced object: missing');
    expect(document.body.textContent).toContain('ZIP object: not created');
    expect(document.body.textContent).toContain('Administrators: Ada');
    expect(document.body.textContent).toContain('User ID: user-1');
  });
});
