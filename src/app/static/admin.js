const state = {
  courseMarker: null,
  userMarker: null,
};

function textCell(value) {
  const cell = document.createElement("td");
  cell.textContent = value === null || value === undefined ? "" : String(value);
  return cell;
}

function setText(id, value) {
  document.getElementById(id).textContent = String(value);
}

function appendCourseRows(courses) {
  const tbody = document.getElementById("admin-course-rows");
  for (const course of courses) {
    const row = document.createElement("tr");
    row.append(
      textCell(course.course_id),
      textCell(course.course_name),
      textCell(course.admin_count),
      textCell(course.max_enrollment),
    );
    tbody.append(row);
  }
}

function appendUserRows(users) {
  const tbody = document.getElementById("admin-user-rows");
  for (const user of users) {
    const row = document.createElement("tr");
    row.append(
      textCell(user.user_name),
      textCell(user.email),
      textCell(user.primary_course_id),
      textCell(user.super_role === "none" ? "no" : user.super_role),
      textCell(`${user.course_count} / ${user.admin_course_count} admin`),
    );
    tbody.append(row);
  }
}

function setMoreButton(id, marker, handler) {
  const button = document.getElementById(id);
  button.hidden = !marker;
  button.onclick = marker ? handler : null;
}

async function loadAdminSummary({ appendCourses = false, appendUsers = false } = {}) {
  const params = new URLSearchParams({ limit: "25" });
  if (appendCourses && state.courseMarker) {
    params.set("course_marker", state.courseMarker);
  }
  if (appendUsers && state.userMarker) {
    params.set("user_marker", state.userMarker);
  }
  const response = await fetch(`${API_BASE}api/admin/summary?${params}`, {
    credentials: "same-origin",
  });
  const payload = await response.json();
  if (!response.ok || payload.error) {
    throw new Error(payload.message || `Admin summary failed with HTTP ${response.status}`);
  }

  setText("admin-course-count", payload.counts.courses);
  setText("admin-user-count", payload.counts.users);
  setText("admin-movie-count", payload.counts.movies);

  if (!appendCourses && !appendUsers) {
    document.getElementById("admin-course-rows").replaceChildren();
    document.getElementById("admin-user-rows").replaceChildren();
    appendCourseRows(payload.courses.items);
    appendUserRows(payload.users.items);
    state.courseMarker = payload.courses.restart_marker;
    state.userMarker = payload.users.restart_marker;
  } else if (appendCourses) {
    appendCourseRows(payload.courses.items);
    state.courseMarker = payload.courses.restart_marker;
  } else if (appendUsers) {
    appendUserRows(payload.users.items);
    state.userMarker = payload.users.restart_marker;
  }

  setMoreButton("admin-more-courses", state.courseMarker, () => loadAdminSummary({ appendCourses: true }));
  setMoreButton("admin-more-users", state.userMarker, () => loadAdminSummary({ appendUsers: true }));
  document.getElementById("admin-bootstrap-note").hidden = !payload.viewer.bootstrap_course_admin;
  document.getElementById("admin-status").textContent = `Read-only access as ${payload.viewer.user_name}`;
}

loadAdminSummary().catch((error) => {
  const status = document.getElementById("admin-status");
  status.className = "admin-error";
  status.textContent = error.message;
});
