const { changeCurrentCourse } = require('current_course');

function coursePicker() {
  document.body.innerHTML = `
    <select id="current-course-select" data-current-course-id="BIO-1">
      <option value="BIO-1">Biology</option>
      <option value="CHEM-2">Chemistry</option>
    </select>
    <span id="current-course-status"></span>`;
  return document.getElementById('current-course-select');
}

describe('current course picker', () => {
  beforeEach(() => {
    global.API_BASE = '/';
    fetch.resetMocks();
  });

  test('saves the selected membership and reloads the page', async () => {
    const select = coursePicker();
    const reload = jest.fn();
    select.value = 'CHEM-2';
    fetch.mockResponseOnce(JSON.stringify({
      error: false,
      course: { course_id: 'CHEM-2', course_name: 'Chemistry' },
    }));

    await changeCurrentCourse(select, reload);

    expect(fetch).toHaveBeenCalledWith('/api/current-course', expect.objectContaining({
      method: 'PATCH',
      body: JSON.stringify({ course_id: 'CHEM-2' }),
    }));
    expect(select.dataset.currentCourseId).toBe('CHEM-2');
    expect(reload).toHaveBeenCalledTimes(1);
  });

  test('restores the previous course when the server rejects the change', async () => {
    const select = coursePicker();
    select.value = 'CHEM-2';
    fetch.mockResponseOnce(JSON.stringify({ error: true, message: 'Course membership required' }), {
      status: 400,
    });

    await changeCurrentCourse(select, jest.fn());

    expect(select.value).toBe('BIO-1');
    const status = document.getElementById('current-course-status');
    expect(status.textContent).toBe('Course membership required');
    expect(status.className).toBe('course-error');
  });
});
