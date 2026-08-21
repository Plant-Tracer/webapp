const TABLE_CONFIG = {
  courses: {
    bodyId: "admin-course-rows", markerParam: "course_marker",
    idKey: "course_id", defaultKey: "course_name",
  },
  users: {
    bodyId: "admin-user-rows", markerParam: "user_marker",
    idKey: "user_id", defaultKey: "user_name",
  },
  movies: {
    bodyId: "admin-movie-rows", markerParam: "movie_marker",
    idKey: "movie_id", defaultKey: "title",
  },
};
const TABLE_NAMES = Object.keys(TABLE_CONFIG);
const state = {
  courses: [],
  users: [],
  movies: [],
  viewerRole: "none",
  verboseDetails: false,
  sort: Object.fromEntries(TABLE_NAMES.map((table) => [
    table,
    { key: TABLE_CONFIG[table].defaultKey, direction: 1 },
  ])),
};

function textCell(value) {
  const cell = document.createElement("td");
  cell.textContent = value === null || value === undefined ? "" : String(value);
  return cell;
}

function epochSeconds(value) {
  const epoch = Number(value);
  return Number.isFinite(epoch) && epoch > 0 ? epoch : null;
}

function formatDate(value) {
  const epoch = epochSeconds(value);
  return epoch === null ? "—" : new Date(epoch * 1000).toLocaleString();
}

function dateCell(value, title = "") {
  const cell = textCell(formatDate(value));
  cell.dataset.sortValue = epochSeconds(value) || 0;
  if (title) {
    cell.title = title;
  }
  return cell;
}

function courseLink(courseId, courseName = courseId) {
  const link = document.createElement("a");
  link.href = `/list?course_id=${encodeURIComponent(courseId)}`;
  link.target = "_blank";
  link.rel = "noopener";
  link.textContent = courseName || courseId;
  link.title = `Open movies for ${courseName || courseId} in a new tab`;
  return link;
}

function setText(id, value) {
  document.getElementById(id).textContent = String(value);
}

function eyeIcon(slashed) {
  const namespace = "http://www.w3.org/2000/svg";
  const icon = document.createElementNS(namespace, "svg");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.setAttribute("aria-hidden", "true");
  const eye = document.createElementNS(namespace, "path");
  eye.setAttribute("d", "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z");
  const pupil = document.createElementNS(namespace, "circle");
  pupil.setAttribute("cx", "12");
  pupil.setAttribute("cy", "12");
  pupil.setAttribute("r", "3");
  icon.append(eye, pupil);
  if (slashed) {
    const slash = document.createElementNS(namespace, "line");
    slash.setAttribute("class", "admin-eye-slash");
    slash.setAttribute("x1", "3");
    slash.setAttribute("y1", "3");
    slash.setAttribute("x2", "21");
    slash.setAttribute("y2", "21");
    icon.append(slash);
  }
  return icon;
}

function courseKeyCell(course) {
  const cell = document.createElement("td");
  const key = document.createElement("code");
  key.className = "admin-course-key";
  const toggle = document.createElement("button");
  toggle.className = "admin-key-toggle";
  toggle.type = "button";
  let hidden = true;
  const render = () => {
    key.textContent = hidden ? "••••••••" : course.course_key;
    const action = hidden ? "Show" : "Hide";
    toggle.replaceChildren(eyeIcon(hidden));
    toggle.setAttribute("aria-label", `${action} course key for ${course.course_name}`);
    toggle.setAttribute("aria-pressed", String(!hidden));
    toggle.title = `${action} course key`;
  };
  toggle.addEventListener("click", () => {
    hidden = !hidden;
    render();
  });
  render();
  cell.append(key, toggle);
  return cell;
}

function courseNameCell(course) {
  const cell = document.createElement("td");
  cell.append(courseLink(course.course_id, course.course_name));
  return cell;
}

function verboseRow(text, dataRow) {
  const row = document.createElement("tr");
  row.className = "admin-verbose-row";
  const cell = textCell(text);
  cell.colSpan = dataRow.cells.length;
  row.append(cell);
  return row;
}

function compactDetails(details) {
  return details.filter((detail) => detail[1] !== null && detail[1] !== undefined && detail[1] !== "")
    .map(([label, value]) => `${label}: ${value}`).join(" · ");
}

function appendCourseRows(courses) {
  const tbody = document.getElementById("admin-course-rows");
  for (const course of courses) {
    const row = document.createElement("tr");
    row.append(
      textCell(course.course_id),
      courseKeyCell(course),
      courseNameCell(course),
      textCell(course.admin_count),
      textCell(`${course.enrollment_count} / ${course.max_enrollment}`),
      dateCell(
        course.display_created_at,
        course.created_at ? "Course creation time" : "First movie upload; course creation time unavailable",
      ),
      dateCell(course.last_movie_activity_at),
    );
    tbody.append(row);
    if (state.verboseDetails) {
      tbody.append(verboseRow(compactDetails([
        ["Course ID", course.course_id],
        ["Administrators", (course.admin_names || []).join(", ") || "none"],
      ]), row));
    }
  }
}

function coursesCell(courses) {
  const cell = document.createElement("td");
  courses.forEach((course, index) => {
    if (index > 0) {
      cell.append(document.createTextNode(", "));
    }
    const name = course.is_admin ? document.createElement("strong") : document.createElement("span");
    name.append(courseLink(course.course_id, course.course_name));
    cell.append(name);
  });
  return cell;
}

function appendUserRows(users) {
  const tbody = document.getElementById("admin-user-rows");
  for (const user of users) {
    const row = document.createElement("tr");
    row.append(
      textCell(user.user_name),
      textCell(user.email),
      textCell(user.default_course_id),
      textCell(user.super_role === "none" ? "no" : user.super_role),
      coursesCell(user.courses),
      dateCell(user.created_at),
      dateCell(user.last_movie_activity_at),
    );
    tbody.append(row);
    if (state.verboseDetails) {
      tbody.append(verboseRow(compactDetails([
        ["User ID", user.user_id],
        ["Primary course ID", user.primary_course_id],
      ]), row));
    }
  }
}

function movieTitleCell(movie) {
  const cell = document.createElement("td");
  if (state.viewerRole === "superadmin" && epochSeconds(movie.uploaded_at)) {
    const link = document.createElement("a");
    link.href = `/analyze?movie_id=${encodeURIComponent(movie.movie_id)}`;
    link.textContent = movie.title;
    cell.append(link);
  } else {
    cell.textContent = movie.title;
  }
  return cell;
}

function movieSizeText(movie) {
  const details = [];
  const frames = Number(movie.total_frames);
  if (Number.isFinite(frames) && frames >= 0) {
    details.push(`${frames.toLocaleString()} frames`);
  }
  const fpm = Number(movie.fpm);
  if (Number.isFinite(frames) && frames > 0 && Number.isFinite(fpm) && fpm > 0) {
    const minutes = Math.max(0, frames - 1) / fpm;
    details.push(`${minutes.toLocaleString(undefined, { maximumFractionDigits: 2 })} min elapsed`);
  }
  const bytes = Number(movie.total_bytes);
  if (Number.isFinite(bytes) && bytes > 0) {
    details.push(`${(bytes / 1000000).toLocaleString(undefined, { maximumFractionDigits: 1 })} MB`);
  }
  return details.length ? details.join(" · ") : "—";
}

async function fetchAdminJson(url, failureLabel, options = {}) {
  const response = await fetch(url, { ...options, credentials: "same-origin" });
  const payload = await response.json();
  if (!response.ok || payload.error) {
    throw new Error(payload.message || `${failureLabel} failed with HTTP ${response.status}`);
  }
  return payload;
}


async function fetchMovieMedia(movieId) {
  return fetchAdminJson(
    `${API_BASE}api/admin/movies/${encodeURIComponent(movieId)}/media`,
    "Movie media request",
  );
}


async function fetchMovieStorageHealth(movieId) {
  return fetchAdminJson(
    `${API_BASE}api/admin/movies/${encodeURIComponent(movieId)}/storage-health`,
    "Storage health",
  );
}


async function loadMovieStorageHealth() {
  const movies = state.movies.filter((movie) => movie.original_object_state === undefined);
  let nextMovie = 0;
  async function loadNextMovie() {
    while (nextMovie < movies.length) {
      const movie = movies[nextMovie];
      nextMovie += 1;
      Object.assign(movie, await fetchMovieStorageHealth(movie.movie_id));
    }
  }
  await Promise.all(Array.from({ length: Math.min(4, movies.length) }, loadNextMovie));
  renderTable("movies");
}

function downloadUrl(url) {
  const link = document.createElement("a");
  link.href = url;
  link.download = "";
  document.body.append(link);
  link.click();
  link.remove();
}

function movieActionsCell(movie) {
  const cell = document.createElement("td");
  cell.className = "admin-actions-cell";
  if (!epochSeconds(movie.uploaded_at)) {
    cell.textContent = "—";
    return cell;
  }
  const button = document.createElement("button");
  button.type = "button";
  button.className = "admin-actions-toggle";
  button.textContent = "⋮";
  button.setAttribute("aria-label", `Actions for ${movie.title}`);
  button.setAttribute("aria-expanded", "false");
  const menu = document.createElement("div");
  menu.className = "admin-actions-menu";
  menu.hidden = true;
  const actions = [
    ["Play", async () => {
      const media = await fetchMovieMedia(movie.movie_id);
      window.open(media.play_url, "_blank", "noopener");
    }],
  ];
  if (movie.has_traced_movie) {
    actions.push(["Download traced", async () => {
      const media = await fetchMovieMedia(movie.movie_id);
      if (!media.traced_download_url) {
        throw new Error("Traced movie is not available");
      }
      downloadUrl(media.traced_download_url);
    }]);
  }
  if (state.viewerRole === "superadmin") {
    actions.push(["Analyze", async () => {
      window.location.assign(`/analyze?movie_id=${encodeURIComponent(movie.movie_id)}`);
    }]);
  }
  for (const [label, action] of actions) {
    const actionButton = document.createElement("button");
    actionButton.type = "button";
    actionButton.textContent = label;
    actionButton.addEventListener("click", async () => {
      menu.hidden = true;
      button.setAttribute("aria-expanded", "false");
      try {
        await action();
      } catch (error) {
        reportAdminError(error);
      }
    });
    menu.append(actionButton);
  }
  button.addEventListener("click", () => {
    menu.hidden = !menu.hidden;
    button.setAttribute("aria-expanded", String(!menu.hidden));
  });
  cell.append(button, menu);
  return cell;
}

function appendMovieRows(movies) {
  const tbody = document.getElementById("admin-movie-rows");
  for (const movie of movies) {
    const row = document.createElement("tr");
    if (!epochSeconds(movie.uploaded_at)) {
      row.classList.add("admin-upload-pending");
      row.title = "Movie record was created but the upload has not completed";
    }
    const courseCell = document.createElement("td");
    courseCell.append(courseLink(movie.course_id, movie.course_name));
    row.append(
      movieTitleCell(movie),
      courseCell,
      textCell(movie.owner_name),
      dateCell(movie.uploaded_at),
      dateCell(movie.last_activity_at),
      textCell(movieSizeText(movie)),
      textCell(movie.state),
      textCell(movie.status),
      movieActionsCell(movie),
    );
    tbody.append(row);
    if (state.verboseDetails) {
      const dimensions = movie.width && movie.height ? `${movie.width} × ${movie.height}` : null;
      tbody.append(verboseRow(compactDetails([
        ["Movie ID", movie.movie_id], ["Description", movie.description],
        ["Dimensions", dimensions], ["FPS", movie.fps], ["FPM", movie.fpm],
        ["Rotation", movie.rotation], ["Trim start", movie.trim_start_frame],
        ["Trim end", movie.trim_end_frame], ["Retrace required", movie.needs_retracing ? "yes" : "no"],
        ["Original object", movie.original_object_state], ["Traced object", movie.traced_object_state],
        ["ZIP object", movie.zip_object_state],
        ["Pending upload age", movie.pending_upload_age_seconds == null
          ? null : `${movie.pending_upload_age_seconds} seconds`],
        ["Research use", movie.research_use], ["Credit by name", movie.credit_by_name],
        ["Attribution", movie.attribution_name],
      ]), row));
    }
  }
}

function sortValue(row, key) {
  if (key === "courses") {
    return row.courses.map((course) => course.course_name).join("\u0000");
  }
  return row[key];
}

function compareValues(left, right) {
  if (typeof left === "number" && typeof right === "number") {
    return left - right;
  }
  return String(left ?? "").localeCompare(String(right ?? ""), undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

function sortedRows(table) {
  const config = TABLE_CONFIG[table];
  const { key, direction } = state.sort[table];
  return [...state[table]].sort((left, right) => (
    direction * (
      compareValues(sortValue(left, key), sortValue(right, key))
      || compareValues(left[config.idKey], right[config.idKey])
    )
  ));
}

function updateSortIndicators(table) {
  const current = state.sort[table];
  document.querySelectorAll(`[data-table="${table}"]`).forEach((button) => {
    const selected = button.dataset.key === current.key;
    button.closest("th").setAttribute(
      "aria-sort",
      selected ? (current.direction === 1 ? "ascending" : "descending") : "none",
    );
    button.querySelector(".admin-sort-indicator").textContent = selected
      ? (current.direction === 1 ? "▲" : "▼")
      : "";
  });
}

function renderTable(table) {
  document.getElementById(TABLE_CONFIG[table].bodyId).replaceChildren();
  const appendRows = {
    courses: appendCourseRows,
    users: appendUserRows,
    movies: appendMovieRows,
  }[table];
  appendRows(sortedRows(table));
  updateSortIndicators(table);
}

function changeSort(table, key) {
  const current = state.sort[table];
  state.sort[table] = {
    key,
    direction: current.key === key ? -current.direction : 1,
  };
  renderTable(table);
}

function bindSortButtons() {
  document.querySelectorAll(".admin-sort").forEach((button) => {
    if (button.dataset.sortBound) {
      return;
    }
    button.dataset.sortBound = "true";
    button.addEventListener("click", () => changeSort(button.dataset.table, button.dataset.key));
  });
}

function bindVerboseDetails() {
  const checkbox = document.getElementById("admin-verbose-details");
  if (!checkbox || checkbox.dataset.bound) {
    return;
  }
  checkbox.dataset.bound = "true";
  checkbox.addEventListener("change", async () => {
    state.verboseDetails = checkbox.checked;
    TABLE_NAMES.forEach(renderTable);
    if (state.verboseDetails) {
      try {
        await loadMovieStorageHealth();
      } catch (error) {
        reportAdminError(error);
      }
    }
  });
}

function existingUserForEmail(email) {
  const normalized = email.trim().toLowerCase();
  return state.users.find((user) => user.email.toLowerCase() === normalized) || null;
}

function populateExistingCourseAdmins() {
  const choices = document.getElementById("admin-existing-course-admins");
  if (!choices) {
    return;
  }
  choices.replaceChildren();
  state.users
    .filter((user) => user.enabled && user.user_name?.trim()
      && user.courses.some((course) => course.is_admin))
    .sort((left, right) => compareValues(left.user_name || left.email, right.user_name || right.email))
    .forEach((user) => {
      const option = document.createElement("option");
      option.value = user.email;
      option.label = user.user_name;
      choices.append(option);
    });
}

function syncCourseAdminName() {
  const email = document.getElementById("admin-course-admin-email");
  const name = document.getElementById("admin-course-admin-name");
  if (!email || !name) {
    return;
  }
  const existingUser = existingUserForEmail(email.value);
  const wasReadOnly = name.readOnly;
  name.readOnly = existingUser !== null;
  if (existingUser) {
    name.value = existingUser.user_name;
  } else if (wasReadOnly) {
    name.value = "";
  }
}

async function submitCourseCreate(form) {
  const submit = document.getElementById("admin-course-submit");
  const formStatus = document.getElementById("admin-course-form-status");
  const fields = new FormData(form);
  submit.disabled = true;
  formStatus.className = "";
  formStatus.textContent = "Creating course...";
  try {
    const payload = await fetchAdminJson(`${API_BASE}api/admin/courses`, "Course creation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.fromEntries(fields.entries())),
    });
    document.getElementById("admin-course-dialog").close();
    const status = document.getElementById("admin-status");
    try {
      await loadAdminSummary();
    } catch (refreshError) {
      status.className = "admin-warning";
      status.textContent = `${payload.message}. Admin list refresh failed: ${refreshError.message}`;
      return;
    }
    status.className = payload.email_sent ? "admin-success" : "admin-warning";
    status.textContent = payload.message;
  } catch (error) {
    formStatus.className = "admin-error";
    formStatus.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
}

function bindCourseCreate() {
  const button = document.getElementById("admin-new-course");
  const dialog = document.getElementById("admin-course-dialog");
  const form = document.getElementById("admin-course-form");
  if (!button || !dialog || !form || button.dataset.bound) {
    return;
  }
  button.dataset.bound = "true";
  button.addEventListener("click", () => {
    form.reset();
    document.getElementById("admin-course-admin-name").readOnly = false;
    const formStatus = document.getElementById("admin-course-form-status");
    formStatus.className = "";
    formStatus.textContent = "";
    populateExistingCourseAdmins();
    dialog.showModal();
  });
  document.getElementById("admin-course-cancel").addEventListener("click", () => dialog.close());
  document.getElementById("admin-course-admin-email").addEventListener("input", syncCourseAdminName);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitCourseCreate(form);
  });
}

function initializeColumnWidths(table) {
  const headers = table.querySelectorAll("thead th");
  let columns = table.querySelectorAll("col");
  if (columns.length !== headers.length) {
    const group = document.createElement("colgroup");
    headers.forEach(() => group.append(document.createElement("col")));
    table.prepend(group);
    columns = group.querySelectorAll("col");
  }
  let totalWidth = 0;
  headers.forEach((header, index) => {
    const width = Math.max(80, Math.round(header.getBoundingClientRect().width));
    columns[index].style.width = `${width}px`;
    totalWidth += width;
  });
  table.style.width = `${totalWidth}px`;
}

function resizeColumn(table, index, width) {
  const columns = table.querySelectorAll("col");
  const currentWidths = [...columns].map((column) => (
    Number.parseFloat(column.style.width) || 80
  ));
  currentWidths[index] = Math.max(80, Math.round(width));
  columns[index].style.width = `${currentWidths[index]}px`;
  table.style.width = `${currentWidths.reduce((total, value) => total + value, 0)}px`;
}

function bindResizableTables() {
  document.querySelectorAll("[data-resizable-table]").forEach((table) => {
    if (table.dataset.resizeBound) {
      return;
    }
    table.dataset.resizeBound = "true";
    initializeColumnWidths(table);
    table.querySelectorAll("thead th").forEach((header, index) => {
      const handle = document.createElement("span");
      handle.className = "admin-resize-handle";
      handle.tabIndex = 0;
      handle.setAttribute("role", "separator");
      handle.setAttribute("aria-orientation", "vertical");
      handle.setAttribute("aria-label", `Resize ${header.textContent.trim()} column`);
      handle.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const startX = event.clientX;
        const startWidth = header.getBoundingClientRect().width;
        handle.setPointerCapture(event.pointerId);
        const move = (moveEvent) => {
          resizeColumn(table, index, startWidth + moveEvent.clientX - startX);
        };
        const finish = () => {
          handle.removeEventListener("pointermove", move);
          handle.removeEventListener("pointerup", finish);
          handle.removeEventListener("pointercancel", finish);
        };
        handle.addEventListener("pointermove", move);
        handle.addEventListener("pointerup", finish);
        handle.addEventListener("pointercancel", finish);
      });
      handle.addEventListener("keydown", (event) => {
        if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") {
          return;
        }
        event.preventDefault();
        const direction = event.key === "ArrowLeft" ? -10 : 10;
        resizeColumn(table, index, header.getBoundingClientRect().width + direction);
      });
      header.append(handle);
    });
  });
}

function reportAdminError(error) {
  const status = document.getElementById("admin-status");
  status.className = "admin-error";
  status.textContent = error.message;
}

function enrichCourseNames() {
  // Courses, users, and movies are downloaded independently. Join them once in
  // browser memory after every bounded page has arrived; this avoids rescanning
  // the courses table during each paginated user or movie API request.
  const names = new Map(state.courses.map((course) => [
    course.course_id,
    course.course_name || course.course_id,
  ]));
  const adminNames = new Map();
  state.users.forEach((user) => {
    const adminName = user.user_name || user.email || user.user_id;
    user.courses.forEach((membership) => {
      membership.course_name = names.get(membership.course_id) || membership.course_id;
      if (membership.is_admin) {
        const courseAdminNames = adminNames.get(membership.course_id) || [];
        courseAdminNames.push(adminName);
        adminNames.set(membership.course_id, courseAdminNames);
      }
    });
  });
  state.courses.forEach((course) => {
    course.admin_names = (adminNames.get(course.course_id) || []).sort();
  });
  state.movies.forEach((movie) => {
    movie.course_name = names.get(movie.course_id) || movie.course_id;
  });

  const firstUploadByCourse = new Map();
  const lastActivityByCourse = new Map();
  const lastActivityByUser = new Map();
  state.movies.forEach((movie) => {
    const uploadedAt = epochSeconds(movie.uploaded_at);
    const lastActivityAt = epochSeconds(movie.last_activity_at)
      || uploadedAt
      || epochSeconds(movie.created_at);
    if (uploadedAt !== null) {
      const current = firstUploadByCourse.get(movie.course_id);
      firstUploadByCourse.set(
        movie.course_id,
        current === undefined ? uploadedAt : Math.min(current, uploadedAt),
      );
    }
    if (lastActivityAt !== null) {
      lastActivityByCourse.set(
        movie.course_id,
        Math.max(lastActivityByCourse.get(movie.course_id) || 0, lastActivityAt),
      );
      lastActivityByUser.set(
        movie.user_id,
        Math.max(lastActivityByUser.get(movie.user_id) || 0, lastActivityAt),
      );
    }
  });
  state.courses.forEach((course) => {
    course.display_created_at = epochSeconds(course.created_at)
      || firstUploadByCourse.get(course.course_id)
      || null;
    course.last_movie_activity_at = lastActivityByCourse.get(course.course_id) || null;
  });
  state.users.forEach((user) => {
    user.last_movie_activity_at = lastActivityByUser.get(user.user_id) || null;
  });
}

async function fetchAdminPage(section, marker = null) {
  const params = new URLSearchParams({ limit: "100", section });
  if (marker) {
    params.set(TABLE_CONFIG[section].markerParam, marker);
  }
  return fetchAdminJson(`${API_BASE}api/admin/summary?${params}`, "Admin summary");
}

async function loadRemainingPages(table, marker) {
  // Product sizing assumes no more than roughly 10 courses with 80 students
  // each. Loading every page is deliberate: complete local datasets make the
  // column sorts global. A larger deployment should move sorting and pagination
  // to the server rather than silently stop after an arbitrary page count.
  let nextMarker = marker;
  while (nextMarker) {
    const payload = await fetchAdminPage(table, nextMarker);
    state[table].push(...payload[table].items);
    nextMarker = payload[table].restart_marker;
  }
}

async function loadAdminSummary() {
  bindSortButtons();
  bindVerboseDetails();
  bindResizableTables();
  bindCourseCreate();
  const status = document.getElementById("admin-status");
  status.className = "";
  status.textContent = "Loading all admin records...";
  const payload = await fetchAdminPage("all");
  state.viewerRole = payload.viewer.super_role;
  setText("admin-course-count", payload.counts.courses);
  setText("admin-user-count", payload.counts.users);
  setText("admin-movie-count", payload.counts.movies);
  TABLE_NAMES.forEach((table) => {
    state[table] = [...payload[table].items];
  });
  await Promise.all(TABLE_NAMES.map(
    (table) => loadRemainingPages(table, payload[table].restart_marker),
  ));
  enrichCourseNames();
  TABLE_NAMES.forEach(renderTable);
  const newCourse = document.getElementById("admin-new-course");
  if (newCourse) {
    newCourse.hidden = state.viewerRole !== "superadmin";
  }
  const accessLabel = state.viewerRole === "superauditor" ? "Read-only" : "Administrative";
  status.textContent = `${accessLabel} access as ${payload.viewer.user_name}. Loaded all records.`;
}

export {
  appendCourseRows,
  appendMovieRows,
  appendUserRows,
  changeSort,
  populateExistingCourseAdmins,
  syncCourseAdminName,
  loadAdminSummary,
  sortedRows,
  state,
};

if (document.getElementById("admin-status")) {
  loadAdminSummary().catch(reportAdminError);
}
