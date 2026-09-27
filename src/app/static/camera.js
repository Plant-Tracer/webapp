import { activeCourseId, appendCourseContext } from './course_context.js';

const CAPTURE_INTERVAL_MS = 15_000;
const FRAME_WIDTH = 640;
const FRAME_HEIGHT = 480;
const FRAME_MAX_BYTES = 2 * 1024 * 1024;
const PROCESSING_TIMEOUT_MS = 5 * 60 * 1000;
const video = document.querySelector('#camera-preview');
const status = document.querySelector('#camera-status');
const stopButton = document.querySelector('#camera-stop');
const retryButton = document.querySelector('#camera-retry');
const analyzeLink = document.querySelector('#camera-analyze');

let stream;
let movieId;
let courseId;
let nextFrameNumber = 0;
let nextCaptureAt = 0;
let captureTimer;
let recording = false;
let captureError;
let outputSize;
const pendingUploads = new Set();

function setStatus(message) {
  status.textContent = message;
}

function formData(fields = {}) {
  const data = new FormData();
  appendCourseContext(data);
  Object.entries(fields).forEach(([key, value]) => data.append(key, value));
  return data;
}

async function postForm(path, fields = {}) {
  const response = await fetch(`${API_BASE}${path}`, { method: 'POST', body: formData(fields) });
  const payload = await response.json();
  if (!response.ok || payload.error) {
    throw new Error(payload.message || `Request failed (${response.status}).`);
  }
  return payload;
}

function stopCameraTracks() {
  if (stream) {
    stream.getTracks().forEach((track) => track.stop());
    stream = null;
  }
  video.srcObject = null;
}

function stopCapturing() {
  recording = false;
  clearTimeout(captureTimer);
  stopCameraTracks();
}

function failCapture(error) {
  if (!recording) return;
  captureError = error;
  stopCapturing();
  setStatus(`Recording stopped because a frame could not be captured or uploaded: ${error.message}`);
}

function canvasFrame() {
  const sourceWidth = video.videoWidth;
  const sourceHeight = video.videoHeight;
  if (!sourceWidth || !sourceHeight) throw new Error('The camera preview is not ready.');

  if (!outputSize) {
    const portrait = sourceHeight > sourceWidth;
    outputSize = portrait
      ? { width: FRAME_HEIGHT, height: FRAME_WIDTH }
      : { width: FRAME_WIDTH, height: FRAME_HEIGHT };
  }
  const { width: outputWidth, height: outputHeight } = outputSize;
  const canvas = document.createElement('canvas');
  canvas.width = outputWidth;
  canvas.height = outputHeight;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Could not prepare a camera frame.');
  context.fillStyle = '#000';
  context.fillRect(0, 0, outputWidth, outputHeight);
  const scale = Math.min(outputWidth / sourceWidth, outputHeight / sourceHeight);
  const width = Math.round(sourceWidth * scale);
  const height = Math.round(sourceHeight * scale);
  context.drawImage(video, (outputWidth - width) / 2, (outputHeight - height) / 2, width, height);

  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob) {
        reject(new Error('The browser could not encode this camera frame.'));
      } else if (blob.size > FRAME_MAX_BYTES) {
        reject(new Error('This camera frame is too large to upload.'));
      } else {
        resolve(blob);
      }
    }, 'image/jpeg', 0.9);
  });
}

async function uploadFrame(frameNumber, blob) {
  const signed = await postForm('api/camera/frame-upload', {
    movie_id: movieId,
    frame_number: String(frameNumber),
  });
  const upload = new FormData();
  Object.entries(signed.presigned_post.fields).forEach(([key, value]) => upload.append(key, value));
  upload.append('file', blob, `${String(frameNumber).padStart(6, '0')}.jpg`);
  const response = await fetch(signed.presigned_post.url, { method: 'POST', body: upload });
  if (!response.ok) throw new Error(`Frame upload failed (${response.status}).`);
}

function captureAndUpload() {
  const frameNumber = nextFrameNumber;
  nextFrameNumber += 1;
  const pending = Promise.resolve().then(canvasFrame).then((blob) => uploadFrame(frameNumber, blob));
  pendingUploads.add(pending);
  pending.then(
    () => pendingUploads.delete(pending),
    (error) => {
      pendingUploads.delete(pending);
      failCapture(error);
    },
  );
}

function scheduleCapture() {
  if (!recording) return;
  const delay = Math.max(0, nextCaptureAt - performance.now());
  captureTimer = setTimeout(() => {
    if (!recording) return;
    captureAndUpload();
    const now = performance.now();
    nextCaptureAt += CAPTURE_INTERVAL_MS;
    if (nextCaptureAt <= now) nextCaptureAt = now + CAPTURE_INTERVAL_MS;
    scheduleCapture();
  }, delay);
}

async function waitForProcessing() {
  const deadline = Date.now() + PROCESSING_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const response = await postForm('api/get-movie-metadata', { movie_id: movieId });
    const metadata = response.metadata;
    if (metadata.status === 'processing failed') {
      throw new Error(metadata.processing_failure_summary || 'Movie processing failed.');
    }
    if (metadata.status === 'ready' && metadata.resized_at) return;
    setStatus('STOP received. Processing the time-lapse movie…');
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error('Movie processing is taking longer than expected. Check the Movies page for its status.');
}

async function finishRecording() {
  stopButton.disabled = true;
  stopCapturing();
  if (captureError) {
    setStatus(`Recording stopped with an upload error: ${captureError.message}`);
    return;
  }
  setStatus('Waiting for captured photos to upload…');
  try {
    await Promise.all([...pendingUploads]);
    if (!nextFrameNumber) throw new Error('No photos were captured.');
    const response = await fetch(`${LAMBDA_API_BASE}resize-api/v1/finish-camera`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-api-key': api_key },
      body: JSON.stringify({ movie_id: movieId }),
    });
    if (!response.ok) throw new Error((await response.text()) || `Could not finish movie (${response.status}).`);
    setStatus('STOP received. Processing the time-lapse movie…');
    await waitForProcessing();
    analyzeLink.href = `analyze?movie_id=${encodeURIComponent(movieId)}&course_id=${encodeURIComponent(courseId || '')}`;
    analyzeLink.hidden = false;
    setStatus(`Movie ${movieId} is ready for analysis.`);
  } catch (error) {
    setStatus(`Could not finish the camera movie: ${error.message}`);
  }
}

async function startRecording() {
  retryButton.hidden = true;
  setStatus('Requesting camera access…');
  try {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('This browser does not provide camera access.');
    }
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
    video.srcObject = stream;
    await video.play();
    courseId = activeCourseId();
    const title = `Camera recording ${new Date().toLocaleString()}`;
    const created = await postForm('api/camera/new-movie', {
      title,
      description: '15-second time-lapse recorded with the Plant Tracer camera.',
    });
    movieId = created.movie_id;
    recording = true;
    stopButton.disabled = false;
    setStatus(`Recording movie ${movieId}. A photo is taken every 15 seconds.`);
    nextCaptureAt = performance.now();
    scheduleCapture();
  } catch (error) {
    stopCameraTracks();
    setStatus(`Could not start the camera: ${error.message}`);
    retryButton.hidden = false;
  }
}

stopButton.addEventListener('click', finishRecording);
retryButton.addEventListener('click', startRecording);
startRecording();
