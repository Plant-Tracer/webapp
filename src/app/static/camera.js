// Plant Tracer's signed-in Camera tab uses the shared capture controller.
// This adapter queues the controller's verified JPEGs in capture order.
// It starts uploading after the abort window or when the user presses DONE.
// Frames upload one at a time, with stable numbers for any retry.
// DONE passes the completed sequence to the movie assembly service.

import { initCamera } from './camera-capture.js?v=1';
import { activeCourseId } from './course_context.js';

const UPLOAD_ATTEMPTS = 3;
const REQUEST_TIMEOUT_MS = 30_000;
const PROCESSING_TIMEOUT_MS = 5 * 60 * 1000;

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function postWithTimeout(url, options, handleResponse) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(url, { method: 'POST', ...options, signal: controller.signal });
    return await handleResponse(response);
  } finally {
    clearTimeout(timer);
  }
}

function postForm(path, fields) {
  const body = new FormData();
  body.set('api_key', api_key);
  Object.entries(fields).forEach(([key, value]) => body.set(key, value));
  return postWithTimeout(`${API_BASE}${path}`, { body }, async (response) => {
    const payload = await response.json();
    if (!response.ok || payload.error) {
      throw new Error(payload.message || `Request failed (${response.status}).`);
    }
    return payload;
  });
}

async function uploadFrame(movieId, number, jpeg) {
  for (let attempt = 1; ; attempt += 1) {
    try {
      const { presigned_post: signed } = await postForm('api/camera/frame-upload', {
        movie_id: movieId, frame_number: number,
      });
      const body = new FormData();
      Object.entries(signed.fields).forEach(([key, value]) => body.set(key, value));
      body.append('file', jpeg, `${String(number).padStart(6, '0')}.jpg`);
      await postWithTimeout(signed.url, { body }, (response) => {
        if (!response.ok) throw new Error(`Frame upload failed (${response.status}).`);
      });
      return;
    } catch (error) {
      if (attempt >= UPLOAD_ATTEMPTS) throw error;
      await wait(attempt * 1000);
    }
  }
}

function newRecordingId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
}

function createRecording({ title, description, interval }, stop) {
  const courseId = activeCourseId();
  const recordingId = newRecordingId();
  const frames = [];
  let movieId;
  let nextFrame = 0;
  let committed = false;
  let draining;
  let finalizationRequested = false;
  let finalizationAccepted = false;

  async function drain() {
    while (frames.length) {
      const jpeg = await frames[0];
      if (!jpeg) {
        frames.length = 0;
        return;
      }
      if (!movieId) {
        const created = await postForm('api/camera/new-movie', {
          title, description, capture_interval_seconds: interval / 1000,
          recording_id: recordingId,
          ...(courseId ? { course_id: courseId } : {}),
        });
        movieId = created.movie_id;
      }
      await uploadFrame(movieId, nextFrame, jpeg);
      nextFrame += 1;
      frames.shift();
    }
  }

  function uploadPending() {
    if (!draining) draining = Promise.resolve().then(drain).finally(() => { draining = undefined; });
    return draining;
  }

  function uploadInBackground() {
    if (!draining) uploadPending().catch(() => stop('A frame upload failed.'));
  }

  function metadata() {
    return postForm('api/get-movie-metadata', { movie_id: movieId }).then((result) => result.metadata);
  }

  function finalize() {
    return postWithTimeout(`${LAMBDA_API_BASE}resize-api/v1/finish-camera`, {
      headers: { 'Content-Type': 'application/json', 'x-api-key': api_key },
      body: JSON.stringify({ movie_id: movieId }),
    }, async (response) => {
      if (!response.ok) {
        throw new Error((await response.text()) || `Movie assembly request failed (${response.status}).`);
      }
    });
  }

  return {
    enqueue(frame) {
      frames.push(frame);
      if (committed) uploadInBackground();
    },
    commit() {
      if (committed) return;
      committed = true;
      uploadInBackground();
    },
    async finish(status) {
      await uploadPending();
      if (!finalizationAccepted) {
        const previous = finalizationRequested ? await metadata() : null;
        if (!previous || previous.status === 'uploading') {
          finalizationRequested = true;
          await finalize();
        }
        finalizationAccepted = true;
      }
      status('Processing the time-lapse movie…');
      const course = courseId ? { course_id: courseId } : {};
      const moviesUrl = `list?${new URLSearchParams(course)}`;
      const deadline = Date.now() + PROCESSING_TIMEOUT_MS;
      let processingError;
      while (Date.now() < deadline) {
        const movie = await metadata();
        if (movie.resized_at) {
          const query = new URLSearchParams({ movie_id: movieId, ...course });
          return { url: `analyze?${query}`, label: 'Analyze this movie', message: 'Movie is ready for analysis.' };
        }
        processingError = movie.status === 'processing failed' ?
          movie.processing_failure_summary || 'Movie processing failed.' : null;
        status(processingError ? 'Movie processing hit an error. Waiting for a retry…' :
          'Processing the time-lapse movie…');
        await wait(1000);
      }
      return { url: moviesUrl, label: 'View movies', message: processingError || 'The movie is still processing.' };
    },
  };
}

function confirmLeaving(event) {
  event.preventDefault();
  event.returnValue = true;
}

function setNavigationBusy(busy) {
  document.body.classList.toggle('camera-busy', busy);
  if (busy) {
    window.addEventListener('beforeunload', confirmLeaving);
  } else {
    window.removeEventListener('beforeunload', confirmLeaving);
  }
}

if (demo_mode) {
  initCamera();
} else {
  initCamera({
    recording: createRecording,
    busy: setNavigationBusy,
    exit: () => {
      const courseId = activeCourseId();
      window.location.assign(courseId ? `list?${new URLSearchParams({ course_id: courseId })}` : 'list');
    },
  });
}
