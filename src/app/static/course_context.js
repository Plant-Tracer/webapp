"use strict";

export const ACTIVE_COURSE_STORAGE_KEY = "planttracer.active_course_id";

function choices() {
  if (typeof course_choices === "undefined" || !Array.isArray(course_choices)) {
    return [];
  }
  return course_choices;
}

function validCourseId(courseId) {
  return Boolean(courseId) && choices().some((course) => course.course_id === courseId);
}

function serverCourseViewId() {
  if (typeof course_view_id === "undefined") {
    return null;
  }
  return course_view_id || null;
}

function authorizedCourseId(courseId) {
  return Boolean(courseId) && (
    courseId === serverCourseViewId() || validCourseId(courseId)
  );
}

function urlCourseId() {
  if (typeof window === "undefined") {
    return null;
  }
  return new URL(window.location.href).searchParams.get("course_id");
}

export function activeCourseId() {
  const candidates = [
    serverCourseViewId(),
    urlCourseId(),
    sessionStorage.getItem(ACTIVE_COURSE_STORAGE_KEY),
    typeof user_default_course_id === "undefined" ? null : user_default_course_id,
    choices()[0]?.course_id,
  ];
  return candidates.find(authorizedCourseId) || null;
}

export function storeActiveCourse(courseId) {
  if (!validCourseId(courseId)) {
    throw new Error("Course membership required");
  }
  sessionStorage.setItem(ACTIVE_COURSE_STORAGE_KEY, courseId);
}

export function appendCourseContext(formData) {
  const courseId = activeCourseId();
  if (courseId) {
    formData.set("course_id", courseId);
  }
  return formData;
}

export function courseName(courseId) {
  return choices().find((course) => course.course_id === courseId)?.course_name || courseId;
}

export function courseUrl(courseId) {
  const url = new URL(window.location.href);
  url.searchParams.set("course_id", courseId);
  return url.toString();
}
