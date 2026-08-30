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
const ADMIN_TABLE_MIN_WIDTH = 1024;
const ADMIN_TABLE_FIT_ALLOWANCE = 1;
const state = {
  courses: [],
  users: [],
  movies: [],
  viewerRole: "none",
  viewerUserId: null,
  viewerCourseIds: [],
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

function formatDate(value, hour12 = undefined) {
  const epoch = epochSeconds(value);
  const options = hour12 === undefined ? undefined : { hour12 };
  return epoch === null ? "—" : new Date(epoch * 1000).toLocaleString(undefined, options);
}

function dateCell(value, title = "", hour12 = undefined) {
  const cell = textCell(formatDate(value, hour12));
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

function administratorLabel(user) {
  const name = user.user_name || user.email || user.user_id;
  return user.email && user.email !== name ? `${name} (${user.email})` : name;
}

function closeActionMenus(exceptMenu = null) {
  document.querySelectorAll(".admin-actions-menu:not([hidden])").forEach((menu) => {
    if (menu === exceptMenu) {
      return;
    }
    menu.hidden = true;
    menu.previousElementSibling?.setAttribute("aria-expanded", "false");
  });
}

function positionActionMenu(button, menu) {
  const buttonRect = button.getBoundingClientRect();
  const margin = 8;
  let left = Math.min(
    buttonRect.right - menu.offsetWidth,
    window.innerWidth - menu.offsetWidth - margin,
  );
  left = Math.max(margin, left);
  let top = buttonRect.bottom + 2;
  if (top + menu.offsetHeight > window.innerHeight - margin) {
    top = Math.max(margin, buttonRect.top - menu.offsetHeight - 2);
  }
  menu.style.left = `${Math.round(left)}px`;
  menu.style.top = `${Math.round(top)}px`;
}

function actionsMenuCell(ariaLabel, actions) {
  const cell = document.createElement("td");
  cell.className = "admin-actions-cell";
  if (!actions.length) {
    cell.textContent = "—";
    return cell;
  }
  const button = document.createElement("button");
  button.type = "button";
  button.className = "admin-actions-toggle";
  button.textContent = "⋮";
  button.setAttribute("aria-label", ariaLabel);
  button.setAttribute("aria-expanded", "false");
  const menu = document.createElement("div");
  menu.className = "admin-actions-menu";
  menu.hidden = true;
  actions.forEach((item) => {
    const actionButton = document.createElement("button");
    actionButton.type = "button";
    actionButton.textContent = item.label;
    actionButton.disabled = Boolean(item.disabled);
    actionButton.title = item.title || "";
    actionButton.addEventListener("click", async () => {
      menu.hidden = true;
      button.setAttribute("aria-expanded", "false");
      try {
        await item.action();
      } catch (error) {
        reportAdminError(error);
      }
    });
    menu.append(actionButton);
  });
  button.addEventListener("click", () => {
    const opening = menu.hidden;
    closeActionMenus(opening ? menu : null);
    menu.hidden = !opening;
    button.setAttribute("aria-expanded", String(opening));
    if (opening) {
      positionActionMenu(button, menu);
    }
  });
  cell.append(button, menu);
  return cell;
}

function bindActionMenuDismissal() {
  if (document.body.dataset.adminActionDismissalBound) {
    return;
  }
  document.body.dataset.adminActionDismissalBound = "true";
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".admin-actions-toggle, .admin-actions-menu")) {
      closeActionMenus();
    }
  });
  window.addEventListener("scroll", () => closeActionMenus(), true);
}

function courseAdministratorCell(course) {
  const cell = document.createElement("td");
  const administrators = course.administrators || [];
  const names = document.createElement("div");
  names.className = "course-admin-names";
  if (administrators.length) {
    administrators.forEach((administrator) => {
      const name = document.createElement("span");
      name.className = "course-admin-name";
      name.textContent = administratorLabel(administrator);
      names.append(name);
    });
  } else {
    names.textContent = "none";
  }
  cell.append(names);
  return cell;
}

function courseActionsCell(course) {
  const canManage = state.viewerRole === "superadmin"
    || state.viewerCourseIds.includes(course.course_id);
  const actions = canManage ? [{
    label: "Manage",
    action: async () => openCourseAdminDialog(course),
  }] : [];
  return actionsMenuCell(`Actions for ${course.course_name}`, actions);
}

function appendCourseRows(courses) {
  const tbody = document.getElementById("admin-course-rows");
  for (const course of courses) {
    const row = document.createElement("tr");
    row.append(
      textCell(course.course_id),
      courseKeyCell(course),
      courseNameCell(course),
      courseAdministratorCell(course),
      textCell(`${course.enrollment_count} / ${course.max_enrollment}`),
      dateCell(
        course.display_created_at,
        course.created_at ? "Course creation time" : "First movie upload; course creation time unavailable",
      ),
      dateCell(course.last_movie_activity_at),
      courseActionsCell(course),
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

function selectedCourseAdminDialogCourse() {
  const dialog = document.getElementById("course-admin-dialog");
  return state.courses.find((course) => course.course_id === dialog.dataset.courseId);
}

function applyCourseAdministratorChange(payload) {
  let user = state.users.find((item) => item.user_id === payload.administrator.user_id);
  if (user) {
    Object.assign(user, payload.administrator);
  } else {
    user = payload.administrator;
    state.users.push(user);
  }
  enrichCourseNames();
  renderTable("courses");
  renderTable("users");
  return user;
}

async function changeCourseAdministrator(course, user, assigned) {
  if (!assigned && !window.confirm(
    `Remove ${administratorLabel(user)} as an administrator of ${course.course_name}? `
    + "The user will remain enrolled in the course.",
  )) {
    return;
  }
  const status = document.getElementById("course-admin-dialog-status");
  status.className = "";
  status.textContent = assigned ? "Adding administrator..." : "Removing administrator...";
  const baseUrl = `${API_BASE}api/admin/courses/${encodeURIComponent(course.course_id)}`
    + "/administrators";
  const url = assigned
    ? baseUrl
    : `${baseUrl}/${encodeURIComponent(user.user_id)}`;
  const options = { method: assigned ? "PUT" : "DELETE" };
  if (assigned) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify({ email: user.email });
  }
  try {
    const payload = await fetchAdminJson(url, "Administrator update", options);
    const changedUser = applyCourseAdministratorChange(payload);
    if (
      !assigned
      && changedUser.user_id === state.viewerUserId
      && state.viewerRole !== "superadmin"
    ) {
      document.getElementById("course-admin-dialog").close();
      await reloadAdminSummary();
      return;
    }
    renderCourseAdminDialog(
      selectedCourseAdminDialogCourse(),
      `${administratorLabel(changedUser)} ${assigned ? "added" : "removed"}.`,
    );
  } catch (error) {
    status.className = "admin-error";
    status.textContent = error.message;
  }
}

function renderCourseAdminDialog(course, message = "") {
  const list = document.getElementById("course-admin-current");
  const input = document.getElementById("course-admin-user-email");
  const choices = document.getElementById("course-admin-user-choices");
  const add = document.getElementById("course-admin-add");
  const status = document.getElementById("course-admin-dialog-status");
  const administrators = course.administrators || [];
  document.getElementById("course-admin-dialog-title").textContent =
    `Administrators for ${course.course_name}`;
  status.className = "";
  status.textContent = message;
  list.replaceChildren();
  administrators.forEach((user) => {
    const item = document.createElement("li");
    const label = document.createElement("span");
    label.textContent = administratorLabel(user);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Remove";
    remove.disabled = administrators.length === 1;
    remove.title = remove.disabled ? "A course must retain at least one administrator" : "";
    remove.addEventListener("click", () => changeCourseAdministrator(course, user, false));
    item.append(label, remove);
    list.append(item);
  });
  choices.replaceChildren();
  const administratorIds = new Set(administrators.map((user) => user.user_id));
  const candidates = state.users.filter((user) => user.enabled && !administratorIds.has(user.user_id));
  candidates.sort((left, right) => administratorLabel(left).localeCompare(administratorLabel(right)));
  candidates.forEach((user) => {
    const option = document.createElement("option");
    option.value = user.email;
    option.label = administratorLabel(user);
    choices.append(option);
  });
  input.value = "";
  add.disabled = true;
}

function openCourseAdminDialog(course) {
  const dialog = document.getElementById("course-admin-dialog");
  dialog.dataset.courseId = course.course_id;
  renderCourseAdminDialog(course);
  dialog.showModal();
}

function bindCourseAdminDialog() {
  const dialog = document.getElementById("course-admin-dialog");
  if (!dialog || dialog.dataset.bound) {
    return;
  }
  dialog.dataset.bound = "true";
  document.getElementById("course-admin-dialog-close").addEventListener("click", () => dialog.close());
  document.getElementById("course-admin-user-email").addEventListener("input", (event) => {
    document.getElementById("course-admin-add").disabled = !event.target.value.trim();
  });
  document.getElementById("course-admin-add").addEventListener("click", () => {
    const course = selectedCourseAdminDialogCourse();
    const email = document.getElementById("course-admin-user-email").value.trim();
    if (course && email) {
      changeCourseAdministrator(course, { email }, true);
    }
  });
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


function superRoleLabel(role) {
  return {
    none: "None",
    superadmin: "Super Admin",
    superauditor: "Super Auditor",
  }[role] || role;
}


async function changeSuperRole(user, newRole) {
  const label = administratorLabel(user);
  const oldRole = user.super_role;
  const removing = newRole === "none";
  let warning;
  if (removing) {
    warning = `Remove ${superRoleLabel(oldRole)} status from ${label}?`;
  } else if (newRole === "superadmin") {
    warning = `Make ${label} a Super Admin? This grants cross-course administrative access.`;
  } else {
    warning = `Make ${label} a Super Auditor? This grants read-only cross-course access.`;
  }
  if (!window.confirm(warning)) {
    return;
  }
  const status = document.getElementById("admin-status");
  status.className = "";
  status.textContent = `Changing ${label} from ${superRoleLabel(oldRole)} to ${superRoleLabel(newRole)}...`;
  const endpointRole = removing ? oldRole : newRole;
  const url = `${API_BASE}api/admin/users/${encodeURIComponent(user.user_id)}/${endpointRole}`;
  try {
    const payload = await fetchAdminJson(url, "Super role update", {
      method: removing ? "DELETE" : "PUT",
    });
    Object.assign(user, payload.user);
    if (user.user_id === state.viewerUserId) {
      await reloadAdminSummary();
      return;
    }
    renderTable("users");
    status.textContent = `${administratorLabel(user)} is now ${superRoleLabel(user.super_role)}.`;
  } catch (error) {
    reportAdminError(error);
  }
}


function superRoleCell(user) {
  return textCell(superRoleLabel(user.super_role));
}


function userRoleActionsCell(user) {
  if (state.viewerRole !== "superadmin") {
    return actionsMenuCell(`Actions for ${administratorLabel(user)}`, []);
  }
  const actions = [];
  if (user.super_role !== "superadmin") {
    actions.push({
      label: "Make Super Admin",
      action: async () => changeSuperRole(user, "superadmin"),
    });
  }
  if (user.super_role !== "superauditor") {
    actions.push({
      label: "Make Super Auditor",
      action: async () => changeSuperRole(user, "superauditor"),
    });
  }
  if (user.super_role !== "none") {
    actions.push({
      label: `Remove ${superRoleLabel(user.super_role)}`,
      action: async () => changeSuperRole(user, "none"),
    });
  }
  return actionsMenuCell(`Actions for ${administratorLabel(user)}`, actions);
}


function appendUserRows(users) {
  const tbody = document.getElementById("admin-user-rows");
  for (const user of users) {
    const row = document.createElement("tr");
    row.append(
      textCell(user.user_name),
      textCell(user.email),
      textCell(user.default_course_id),
      superRoleCell(user),
      coursesCell(user.courses),
      dateCell(user.created_at),
      dateCell(user.last_movie_activity_at),
      userRoleActionsCell(user),
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
  cell.className = "admin-movie-title";
  cell.title = movie.title;
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
    details.push(frames.toLocaleString());
  }
  const bytes = Number(movie.total_bytes);
  if (Number.isFinite(bytes) && bytes > 0) {
    const megabytes = bytes / 1000000;
    const maximumFractionDigits = megabytes < 10 ? 1 : 0;
    details.push(`${megabytes.toLocaleString(undefined, { maximumFractionDigits })}MB`);
  }
  const fpm = Number(movie.fpm);
  if (Number.isFinite(frames) && frames > 0 && Number.isFinite(fpm) && fpm > 0) {
    const minutes = Math.max(0, frames - 1) / fpm;
    details.push(`${Math.round(minutes)} min`);
  }
  return details.length ? details.join(" / ") : "—";
}

async function fetchAdminJson(url, failureLabel, options = {}) {
  const response = await fetch(url, { ...options, credentials: "same-origin" });
  let payload;
  try {
    payload = await response.json();
  } catch (_error) {
    throw new Error(`${failureLabel} failed with HTTP ${response.status}`);
  }
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
  if (!epochSeconds(movie.uploaded_at)) {
    return actionsMenuCell(`Actions for ${movie.title}`, []);
  }
  const actions = [
    { label: "Play", action: async () => {
      const media = await fetchMovieMedia(movie.movie_id);
      window.open(media.play_url, "_blank", "noopener");
    } },
  ];
  if (movie.has_traced_movie) {
    actions.push({ label: "Download traced", action: async () => {
      const media = await fetchMovieMedia(movie.movie_id);
      if (!media.traced_download_url) {
        throw new Error("Traced movie is not available");
      }
      downloadUrl(media.traced_download_url);
    } });
  }
  if (state.viewerRole === "superadmin") {
    actions.push({ label: "Analyze", action: async () => {
      window.location.assign(`/analyze?movie_id=${encodeURIComponent(movie.movie_id)}`);
    } });
  }
  return actionsMenuCell(`Actions for ${movie.title}`, actions);
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
      dateCell(movie.uploaded_at, "", false),
      dateCell(movie.last_activity_at, "", false),
      textCell(movieSizeText(movie)),
      textCell(movie.state),
      textCell(movie.status),
      movieActionsCell(movie),
    );
    tbody.append(row);
    if (state.verboseDetails) {
      const dimensions = movie.width && movie.height ? `${movie.width} × ${movie.height}` : null;
      tbody.append(verboseRow(compactDetails([
        ["Title", movie.title], ["Movie ID", movie.movie_id],
        ["Description", movie.description],
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
  const containerWidth = table.closest(".admin-table-scroll")?.clientWidth || 0;
  table.style.width = `${totalWidth}px`;
  resizeWholeTable(table, Math.max(containerWidth - ADMIN_TABLE_FIT_ALLOWANCE, ADMIN_TABLE_MIN_WIDTH));
}

function configuredColumnWidths(table) {
  return [...table.querySelectorAll("col")].map((column) => (
    Number.parseFloat(column.style.width) || 80
  ));
}

function positionTableWidthHandle(table) {
  const handle = table.closest(".admin-table-scroll")
    ?.querySelector(".admin-table-width-handle");
  if (!handle) {
    return;
  }
  const width = Number.parseFloat(table.style.width)
    || table.getBoundingClientRect().width;
  handle.style.left = `${Math.max(0, Math.round(width))}px`;
}

function applyTableWidth(table, widths) {
  const columns = table.querySelectorAll("col");
  widths.forEach((width, index) => {
    columns[index].style.width = `${Math.max(80, Math.round(width))}px`;
  });
  const total = widths.reduce((sum, width) => sum + Math.max(80, Math.round(width)), 0);
  table.style.width = `${total}px`;
  positionTableWidthHandle(table);
}

function resizeWholeTable(table, requestedWidth) {
  const widths = configuredColumnWidths(table);
  const currentWidth = widths.reduce((sum, width) => sum + width, 0);
  if (!widths.length || !currentWidth) {
    return;
  }
  const containerWidth = table.closest(".admin-table-scroll")?.clientWidth || 0;
  const containerFitWidth = Math.max(0, containerWidth - ADMIN_TABLE_FIT_ALLOWANCE);
  const targetWidth = Math.max(
    ADMIN_TABLE_MIN_WIDTH,
    containerFitWidth,
    widths.length * 80,
    Math.round(requestedWidth),
  );
  const scale = targetWidth / currentWidth;
  const scaled = widths.map((width) => Math.max(80, Math.round(width * scale)));
  const scaledTotal = scaled.reduce((sum, width) => sum + width, 0);
  let adjustment = targetWidth - scaledTotal;
  if (adjustment >= 0) {
    scaled[scaled.length - 1] += adjustment;
  } else {
    for (let index = scaled.length - 1; index >= 0 && adjustment < 0; index -= 1) {
      const reduction = Math.min(scaled[index] - 80, -adjustment);
      scaled[index] -= reduction;
      adjustment += reduction;
    }
  }
  applyTableWidth(table, scaled);
}

function fitTableToContainer(table) {
  const containerWidth = table.closest(".admin-table-scroll")?.clientWidth || 0;
  const tableWidth = Number.parseFloat(table.style.width)
    || table.getBoundingClientRect().width;
  const targetWidth = Math.max(
    containerWidth - ADMIN_TABLE_FIT_ALLOWANCE,
    ADMIN_TABLE_MIN_WIDTH,
  );
  if (Math.round(tableWidth) !== Math.round(targetWidth)) {
    resizeWholeTable(table, targetWidth);
  } else {
    positionTableWidthHandle(table);
  }
}

function resizeColumn(table, index, width) {
  const currentWidths = configuredColumnWidths(table);
  currentWidths[index] = Math.max(80, Math.round(width));
  const containerWidth = table.closest(".admin-table-scroll")?.clientWidth || 0;
  const containerFitWidth = Math.max(0, containerWidth - ADMIN_TABLE_FIT_ALLOWANCE);
  const totalWidth = currentWidths.reduce((total, value) => total + value, 0);
  if (totalWidth < containerFitWidth) {
    const fillIndex = index === currentWidths.length - 1 ? 0 : currentWidths.length - 1;
    currentWidths[fillIndex] += containerFitWidth - totalWidth;
  }
  applyTableWidth(table, currentWidths);
}

function bindResizableTables() {
  document.querySelectorAll("[data-resizable-table]").forEach((table) => {
    if (table.dataset.resizeBound) {
      return;
    }
    table.dataset.resizeBound = "true";
    initializeColumnWidths(table);
    const container = table.closest(".admin-table-scroll");
    if (container) {
      const tableHandle = document.createElement("span");
      tableHandle.className = "admin-table-width-handle";
      tableHandle.tabIndex = 0;
      tableHandle.setAttribute("role", "separator");
      tableHandle.setAttribute("aria-orientation", "vertical");
      tableHandle.setAttribute("aria-label", "Resize entire table");
      tableHandle.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        const startX = event.clientX;
        const startWidth = Number.parseFloat(table.style.width)
          || table.getBoundingClientRect().width;
        tableHandle.setPointerCapture(event.pointerId);
        const move = (moveEvent) => {
          resizeWholeTable(table, startWidth + moveEvent.clientX - startX);
        };
        const finish = () => {
          tableHandle.removeEventListener("pointermove", move);
          tableHandle.removeEventListener("pointerup", finish);
          tableHandle.removeEventListener("pointercancel", finish);
        };
        tableHandle.addEventListener("pointermove", move);
        tableHandle.addEventListener("pointerup", finish);
        tableHandle.addEventListener("pointercancel", finish);
      });
      tableHandle.addEventListener("keydown", (event) => {
        if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") {
          return;
        }
        event.preventDefault();
        const direction = event.key === "ArrowLeft" ? -20 : 20;
        const width = Number.parseFloat(table.style.width)
          || table.getBoundingClientRect().width;
        resizeWholeTable(table, width + direction);
      });
      container.append(tableHandle);
      positionTableWidthHandle(table);
      if (typeof ResizeObserver !== "undefined") {
        const observer = new ResizeObserver(() => fitTableToContainer(table));
        observer.observe(container);
      }
    }
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
    course.administrators = state.users.filter((user) => user.courses.some(
      (membership) => membership.course_id === course.course_id && membership.is_admin,
    ));
    course.admin_names = (adminNames.get(course.course_id) || []).sort();
    course.admin_count = course.administrators.length;
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


async function reloadAdminSummary() {
  state.viewerRole = "none";
  state.viewerUserId = null;
  state.viewerCourseIds = [];
  const newCourse = document.getElementById("admin-new-course");
  if (newCourse) {
    newCourse.hidden = true;
  }
  TABLE_NAMES.forEach((table) => {
    state[table] = [];
    renderTable(table);
  });
  try {
    await loadAdminSummary();
  } catch (error) {
    reportAdminError(error);
  }
}


async function loadAdminSummary() {
  bindSortButtons();
  bindVerboseDetails();
  bindResizableTables();
  bindActionMenuDismissal();
  bindCourseCreate();
  bindCourseAdminDialog();
  const status = document.getElementById("admin-status");
  status.className = "";
  status.textContent = "Loading all admin records...";
  const payload = await fetchAdminPage("all");
  state.viewerRole = payload.viewer.super_role;
  state.viewerUserId = payload.viewer.user_id;
  state.viewerCourseIds = [...(payload.viewer.course_ids || [])];
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
  applyCourseAdministratorChange,
  changeSort,
  fitTableToContainer,
  populateExistingCourseAdmins,
  resizeWholeTable,
  syncCourseAdminName,
  openCourseAdminDialog,
  loadAdminSummary,
  sortedRows,
  state,
};

if (document.getElementById("admin-status")) {
  loadAdminSummary().catch(reportAdminError);
}
