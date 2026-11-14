// Standalone camera prototype with setup, recording, and a completion summary.
// The live preview uses the browser's camera and never creates a server movie.
// A ten-second lead-in gives time to move into position before the first frame.
// Monotonic deadlines drive both countdowns, shutters, and recording limits.
// Each shutter draws the image and its label before encoding a local JPEG.
// The demo tracks encoding results and discards the JPEGs after encoding.
// The summary reports the frame count after the live camera is released.

const $ = (id) => document.getElementById(id);
const video = $('preview');
const setup = $('setup');
const startButton = $('start');
const abortButton = $('abort-recording');
const flash = $('flash');
const progress = $('progress');
const countdown = $('countdown');
const startCountdown = $('start-countdown');
const START_DELAY_MS = 10_000;
const ABORT_WINDOW_MS = 60_000;
const TICK_MS = 50;
const MAX_SHUTTER_SOUNDS = 10;
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const timeZoneName = new Intl.DateTimeFormat('en-US', { timeZoneName: 'short' });
const characterSegments = typeof Intl.Segmenter === 'function' ? new Intl.Segmenter() : undefined;

let screen = 'setup';
let stream;
let cameraRequest = 0;
let session;
let audio;
let flashAnimation;

const pad = (value) => String(value).padStart(2, '0');

function localTimestamp(date) {
  const offset = -date.getTimezoneOffset();
  const hours = pad(Math.floor(Math.abs(offset) / 60));
  const minutes = pad(Math.abs(offset) % 60);
  const zone = timeZoneName.formatToParts(date).find(({ type }) => type === 'timeZoneName').value;
  const day = [date.getFullYear(), pad(date.getMonth() + 1), pad(date.getDate())].join('-');
  const time = [date.getHours(), date.getMinutes(), date.getSeconds()].map(pad).join(':');
  return `${day} ${time}${offset < 0 ? '-' : '+'}${hours}:${minutes} ${zone}`;
}

function showScreen(next) {
  screen = next;
  $('step').textContent = {
    home: 'Camera demo', setup: 'Setup', starting: 'Get ready', recording: 'Recording', summary: 'Done',
  }[next];
  $('home').hidden = next !== 'home';
  $('camera').hidden = next === 'home';
  for (const panel of [setup, $('starting'), $('recording'), $('summary')]) {
    panel.hidden = panel.id !== next;
  }
  $('preview-panel').hidden = next === 'summary';
  $('status').textContent = '';
}

function releasePreview() {
  cameraRequest += 1;
  stream?.getTracks().forEach((track) => track.stop());
  stream = undefined;
  video.srcObject = null;
  startButton.disabled = true;
}

async function openPreview() {
  const request = ++cameraRequest;
  $('enable-camera').hidden = true;
  $('status').textContent = 'Opening the camera…';
  try {
    if (!window.isSecureContext) throw new Error('Use localhost or a trusted HTTPS address.');
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('Camera access is unavailable in this browser.');
    const opened = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' } },
      audio: false,
    });
    if (request !== cameraRequest) {
      opened.getTracks().forEach((track) => track.stop());
      return;
    }
    stream = opened;
    video.srcObject = opened;
    await video.play();
    if (request !== cameraRequest) return;
    startButton.disabled = false;
    $('status').textContent = '';
    const track = opened.getVideoTracks()[0];
    track.addEventListener('mute', () => {
      if (opened !== stream) return;
      cancelStart('Countdown canceled because the camera was paused.');
      finish('Recording ended because the camera was paused.');
    });
    track.addEventListener('ended', () => {
      if (opened !== stream) return;
      if (screen === 'recording') {
        finish('The camera disconnected.');
      } else {
        if (screen === 'starting') cancelStart();
        releasePreview();
        $('status').textContent = 'The camera disconnected.';
        $('enable-camera').hidden = false;
      }
    }, { once: true });
  } catch (error) {
    if (request !== cameraRequest) return;
    releasePreview();
    $('status').textContent = `Could not open the camera. ${error.message}`;
    $('enable-camera').hidden = false;
  }
}

function beep(frequency, volume) {
  if (audio?.state !== 'running' || volume <= 0) return;
  const tone = audio.createOscillator();
  const gain = audio.createGain();
  const now = audio.currentTime;
  tone.frequency.value = frequency;
  gain.gain.setValueAtTime(volume * 0.2, now);
  gain.gain.exponentialRampToValueAtTime(0.001, now + 0.07);
  tone.connect(gain).connect(audio.destination);
  tone.start(now);
  tone.stop(now + 0.075);
}

function drawFrame(current, now, takenAt, index) {
  const { videoWidth: width, videoHeight: height } = video;
  if (!width || !height) throw new Error('The camera image is unavailable.');
  const canvas = document.createElement('canvas');
  [canvas.width, canvas.height] = current.size;
  const context = canvas.getContext('2d');
  const scale = Math.min(canvas.width / width, canvas.height / height);
  context.fillStyle = '#000';
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(video, (canvas.width - width * scale) / 2, (canvas.height - height * scale) / 2,
    width * scale, height * scale);
  const text = `${index}  ${Math.round((now - current.started) / 1000)} s  ${localTimestamp(takenAt)}`;
  context.font = 'bold 14px system-ui, sans-serif';
  context.textBaseline = 'middle';
  const labelWidth = Math.ceil(context.measureText(text).width) + 12;
  const left = canvas.width - labelWidth - 6;
  context.fillStyle = '#124f9e';
  context.fillRect(left, 6, labelWidth, 24);
  context.fillStyle = '#fff';
  context.fillText(text, left + 6, 18);
  return new Promise((resolve) => canvas.toBlob((blob) => resolve(Boolean(blob)), 'image/jpeg', 0.9));
}

function capture(current, now) {
  if (!cameraReady()) throw new Error('Recording ended because the camera was unavailable.');
  const index = current.frames.length;
  const frame = drawFrame(current, now, new Date(), index);
  current.frames.push(frame);
  $('frame-count').textContent = index + 1;
  flashAnimation?.cancel();
  flashAnimation = flash.animate([{ opacity: reducedMotion.matches ? 0.25 : 1 }, { opacity: 0 }],
    { duration: reducedMotion.matches ? 120 : 340, easing: 'ease-out' });
  beep(880, 1 - index / (MAX_SHUTTER_SOUNDS - 1));
}

function tick(current) {
  const now = performance.now();
  if (now >= current.endsAt) {
    finish('Maximum duration reached.');
    return;
  }
  const remaining = Math.max(0, current.nextAt - now);
  abortButton.hidden = now >= current.abortAt;
  if (remaining === 0) {
    try {
      capture(current, now);
    } catch (error) {
      finish(error.message);
      return;
    }
    const capturedAt = performance.now();
    const slot = Math.floor((capturedAt - current.started) / current.interval) + 1;
    const deadline = current.started + slot * current.interval;
    // Subtraction can round down at an exact slot boundary.
    current.nextAt = deadline > capturedAt ? deadline : current.started + (slot + 1) * current.interval;
  }
  const nextBoundary = Math.min(current.nextAt, current.endsAt);
  const timeLeft = Math.max(0, nextBoundary - performance.now());
  const seconds = Math.ceil(timeLeft / 1000);
  const label = current.nextAt < current.endsAt ? 'Next shutter' : 'Recording ends in';
  if ($('countdown-label').textContent !== label) $('countdown-label').textContent = label;
  progress.value = 1 - Math.min(1, timeLeft / current.interval);
  countdown.textContent = `${Math.floor(seconds / 60)}:${pad(seconds % 60)}`;
  const nextEvent = Math.min(nextBoundary, abortButton.hidden ? Infinity : current.abortAt);
  current.timer = setTimeout(() => tick(current), Math.max(0, Math.min(TICK_MS, nextEvent - performance.now())));
}

async function holdScreenAwake(current) {
  try {
    const lock = await navigator.wakeLock?.request('screen');
    if (session === current && (screen === 'starting' || screen === 'recording')) {
      current.wakeLock = lock;
    } else {
      await lock?.release();
    }
  } catch {
    // The device can decline a wake lock, for example in low-power mode.
  }
}

function prepareRecording(event) {
  event.preventDefault();
  if (startButton.disabled || screen !== 'setup' || !video.videoWidth) return;
  const title = $('title').value.trim();
  const description = $('description').value.trim();
  for (const [id, label, value] of [['title', 'Title', title], ['description', 'Description', description]]) {
    const field = $(id);
    if ([...(characterSegments?.segment(value) ?? value)].length < field.minLength) {
      field.setCustomValidity(`${label} must have at least four characters.`);
      field.reportValidity();
      return;
    }
  }
  const current = {
    title,
    description,
    interval: Number($('interval').value) * 1000,
    duration: Number($('duration').value) * 3_600_000,
    startAt: performance.now() + START_DELAY_MS,
    frames: [],
  };
  session = current;
  try {
    if (!audio && window.AudioContext) audio = new AudioContext();
    if (audio && audio.state !== 'running') current.audioReady = audio.resume().catch(() => {});
  } catch {
    // The preview and capture can continue when browser audio is unavailable.
  }
  if (document.fullscreenEnabled) {
    document.documentElement.requestFullscreen().then(() => {
      if (screen !== 'starting' && screen !== 'recording') exitFullscreen();
    }).catch(() => {});
  }
  showScreen('starting');
  $('cancel-start').focus({ preventScroll: true });
  holdScreenAwake(current);
  tickStartCountdown(current);
}

function tickStartCountdown(current) {
  if (document.hidden) {
    cancelStart('Countdown canceled when the camera went into the background.');
    return;
  }
  const remaining = current.startAt - performance.now();
  if (remaining <= 0) {
    startRecording(current);
    return;
  }
  const seconds = Math.ceil(remaining / 1000);
  if (current.countdownSeconds !== seconds) {
    current.countdownSeconds = seconds;
    startCountdown.textContent = seconds;
    if (seconds === START_DELAY_MS / 1000 && audio?.state !== 'running' && current.audioReady) {
      current.audioReady.then(() => {
        if (session === current && performance.now() < current.startAt - START_DELAY_MS + 1000) beep(660, 0.7);
      });
    } else {
      beep(660, 0.7);
    }
  }
  current.timer = setTimeout(() => tickStartCountdown(current), remaining - (seconds - 1) * 1000);
}

function cameraReady() {
  const track = stream?.getVideoTracks()[0];
  return track?.readyState === 'live' && !track.muted && video.readyState >= video.HAVE_CURRENT_DATA;
}

function startRecording(current) {
  if (!cameraReady()) {
    cancelStart('The camera is unavailable. Wait for the preview to resume before starting.');
    return;
  }
  current.started = performance.now();
  current.nextAt = current.started;
  current.endsAt = current.started + current.duration;
  current.abortAt = current.started + ABORT_WINDOW_MS;
  current.size = video.videoWidth >= video.videoHeight ? [640, 480] : [480, 640];
  showScreen('recording');
  $('start-time').textContent = new Date().toLocaleTimeString();
  $('frame-count').textContent = '0';
  $('done').focus({ preventScroll: true });
  tick(current);
}

function releaseCaptureResources(current) {
  clearTimeout(current.timer);
  current.wakeLock?.release().catch(() => {});
}

function exitFullscreen() {
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
}

function cancelStart(reason = '') {
  if (screen !== 'starting') return;
  releaseCaptureResources(session);
  session = undefined;
  exitFullscreen();
  showScreen('setup');
  $('status').textContent = reason;
  startButton.focus({ preventScroll: true });
}

function stopRecording(current) {
  releaseCaptureResources(current);
  flashAnimation?.cancel();
  releasePreview();
  exitFullscreen();
}

async function finish(reason) {
  if (screen !== 'recording') return;
  const current = session;
  showScreen('summary');
  stopRecording(current);
  $('summary-title').textContent = current.title;
  $('summary-description').textContent = current.description;
  $('summary-count').textContent = 'Finishing capture…';
  $('new-recording').focus({ preventScroll: true });
  const results = await Promise.all(current.frames);
  if (session !== current) return;
  const count = results.filter(Boolean).length;
  $('summary-count').textContent = `${count} ${count === 1 ? 'frame' : 'frames'} captured`;
  $('status').textContent = [reason, count < results.length ? 'Some frames could not be encoded.' : '']
    .filter(Boolean).join(' ');
}

function abortSetup() {
  releasePreview();
  returnHome();
}

function returnHome() {
  setup.reset();
  showScreen('home');
  $('open-camera').focus();
}

function reset() {
  session = undefined;
  setup.reset();
  showScreen('setup');
  openPreview();
}

setup.addEventListener('submit', prepareRecording);
for (const field of [$('title'), $('description')]) {
  field.addEventListener('input', () => field.setCustomValidity(''));
}
setup.addEventListener('reset', () => {
  $('title').setCustomValidity('');
  $('description').setCustomValidity('');
});
$('enable-camera').addEventListener('click', openPreview);
$('abort-setup').addEventListener('click', abortSetup);
$('open-camera').addEventListener('click', reset);
$('cancel-start').addEventListener('click', () => cancelStart());
$('done').addEventListener('click', () => finish(''));
abortButton.addEventListener('click', () => {
  if (screen !== 'recording' || performance.now() >= session.abortAt) return;
  stopRecording(session);
  session = undefined;
  returnHome();
});
$('new-recording').addEventListener('click', reset);
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) return;
  cancelStart('Countdown canceled when the camera went into the background.');
  finish('Recording ended when the camera went into the background.');
});

openPreview();
