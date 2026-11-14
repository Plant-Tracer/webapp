// Standalone camera prototype with setup, recording, and a completion summary.
// The live preview uses the browser's camera and never creates a server movie.
// A ten-second lead-in gives time to move into position before the first frame.
// Monotonic deadlines drive both countdowns, shutters, and recording limits.
// Each shutter normalizes the image to the first frame and draws its timestamp.
// The demo checks each JPEG's capture metadata before discarding the image.
// The summary reports the frame count after the live camera is released.

const $ = (id) => document.getElementById(id);
const video = $('preview');
const setup = $('setup');
const startButton = $('start');
const motionButton = $('enable-motion');
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
const ascii = new TextEncoder();

let screen = 'setup';
let stream;
let cameraRequest = 0;
let session;
let audio;
let flashAnimation;
let deviceAngle;
let flatReference;

const pad = (value) => String(value).padStart(2, '0');

function captureTime(date) {
  const offset = -date.getTimezoneOffset();
  const hours = pad(Math.floor(Math.abs(offset) / 60));
  const minutes = pad(Math.abs(offset) % 60);
  const zone = timeZoneName.formatToParts(date).find(({ type }) => type === 'timeZoneName').value;
  const day = [String(date.getFullYear()).padStart(4, '0'), pad(date.getMonth() + 1), pad(date.getDate())];
  const time = [date.getHours(), date.getMinutes(), date.getSeconds()].map(pad).join(':');
  const utcOffset = `${offset < 0 ? '-' : '+'}${hours}:${minutes}`;
  return {
    label: `${day.join('-')} ${time}${utcOffset} ${zone}`,
    exifDate: `${day.join(':')} ${time}`,
    utcOffset,
    milliseconds: String(date.getMilliseconds()).padStart(3, '0'),
  };
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
  document.querySelector('main').inert = next === 'starting';
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

function addCaptureExif(jpeg, time, width, height) {
  const asciiTag = (tag, value) => [tag, 2, value.length + 1, ascii.encode(`${value}\0`)];
  const original = [
    [0x9000, 7, 4, ascii.encode('0232')],
    asciiTag(0x9003, time.exifDate),
    asciiTag(0x9011, time.utcOffset),
    [0x9101, 7, 4, Uint8Array.of(1, 2, 3, 0)],
    asciiTag(0x9291, time.milliseconds),
    [0xa000, 7, 4, ascii.encode('0100')],
    [0xa001, 3, 1, 1],
    [0xa002, 4, 1, width],
    [0xa003, 4, 1, height],
  ];
  const directorySize = (entries) => 2 + 12 * entries + 4;
  const primary = [
    [0x0112, 3, 1, 1],
    [0x011a, 5, 1, Uint8Array.of(72, 0, 0, 0, 1, 0, 0, 0)],
    [0x011b, 5, 1, Uint8Array.of(72, 0, 0, 0, 1, 0, 0, 0)],
    [0x0128, 3, 1, 2],
    [0x0213, 3, 1, 1],
  ];
  const exifOffset = 8 + directorySize(primary.length + 1);
  primary.push([0x8769, 4, 1, exifOffset]);
  let dataOffset = exifOffset + directorySize(original.length);
  const dataSize = [...primary, ...original].reduce((size, [, , , value]) =>
    size + (value.length > 4 ? value.length + value.length % 2 : 0), 0);
  const app1 = new Uint8Array(10 + dataOffset + dataSize);
  const view = new DataView(app1.buffer);
  view.setUint16(0, 0xffe1);
  view.setUint16(2, app1.length - 2);
  app1.set(ascii.encode('Exif\0\0II'), 4);
  view.setUint16(12, 42, true);
  view.setUint32(14, 8, true);
  for (const [start, entries] of [[8, primary], [exifOffset, original]]) {
    view.setUint16(10 + start, entries.length, true);
    entries.forEach(([tag, type, count, value], index) => {
      const entry = 12 + start + 12 * index;
      view.setUint16(entry, tag, true);
      view.setUint16(entry + 2, type, true);
      view.setUint32(entry + 4, count, true);
      if (typeof value === 'number') {
        view.setUint32(entry + 8, value, true);
      } else if (value.length <= 4) {
        app1.set(value, entry + 8);
      } else {
        view.setUint32(entry + 8, dataOffset, true);
        app1.set(value, 10 + dataOffset);
        dataOffset += value.length + value.length % 2;
      }
    });
  }
  return writeAndCheckExif(jpeg, app1, time);
}

async function writeAndCheckExif(jpeg, app1, time) {
  if (jpeg?.type !== 'image/jpeg') return false;
  const bytes = new DataView(await jpeg.arrayBuffer());
  const end = bytes.byteLength - 2;
  if (end < 4 || bytes.getUint16(0) !== 0xffd8 || bytes.getUint16(end) !== 0xffd9) return false;
  const parts = [jpeg.slice(0, 2), app1];
  let offset = 2;
  // Keep the encoder's color metadata and image data, replacing JFIF and prior EXIF headers.
  while (offset + 4 <= end) {
    const marker = bytes.getUint16(offset);
    if (marker === 0xffda) break;
    if ((marker & 0xff00) !== 0xff00) return false;
    const length = bytes.getUint16(offset + 2);
    const next = offset + 2 + length;
    if (length < 2 || next > end) return false;
    const jfif = marker === 0xffe0 && length >= 7 && bytes.getUint32(offset + 4) === 0x4a464946
      && bytes.getUint8(offset + 8) === 0;
    const exif = marker === 0xffe1 && length >= 8 && bytes.getUint32(offset + 4) === 0x45786966
      && bytes.getUint16(offset + 8) === 0;
    if (!jfif && !exif) parts.push(jpeg.slice(offset, next));
    offset = next;
  }
  if (offset + 4 > end) return false;
  const result = new Blob([...parts, jpeg.slice(offset)], { type: 'image/jpeg' });
  const segment = new DataView(await result.slice(2, 2 + app1.length).arrayBuffer());
  if (segment.getUint16(0) !== 0xffe1 || segment.getUint16(2) !== app1.length - 2
      || segment.getUint32(4) !== 0x45786966 || segment.getUint32(10) !== 0x49492a00) return false;
  const findTag = (directory, tag) => {
    const count = segment.getUint16(10 + directory, true);
    for (let index = 0; index < count; index += 1) {
      const entry = 12 + directory + 12 * index;
      if (segment.getUint16(entry, true) === tag) return entry;
    }
    return -1;
  };
  const pointer = findTag(segment.getUint32(14, true), 0x8769);
  if (pointer < 0) return false;
  const directory = segment.getUint32(pointer + 8, true);
  return [[0x9003, time.exifDate], [0x9011, time.utcOffset], [0x9291, time.milliseconds]].every(([tag, value]) => {
    const entry = findTag(directory, tag);
    if (entry < 0 || segment.getUint16(entry + 2, true) !== 2
        || segment.getUint32(entry + 4, true) !== value.length + 1) return false;
    const offset = value.length < 4 ? entry + 8 : 10 + segment.getUint32(entry + 8, true);
    return ascii.encode(`${value}\0`).every((byte, index) => segment.getUint8(offset + index) === byte);
  });
}

function screenAngle() {
  return window.screen.orientation?.angle ?? window.orientation ?? 0;
}

function readDeviceAngle({ alpha, beta, gamma }) {
  if (!Number.isFinite(beta) || !Number.isFinite(gamma)) return;
  const pitch = beta * Math.PI / 180;
  const x = -Math.cos(pitch) * Math.sin(gamma * Math.PI / 180);
  const y = Math.sin(pitch);
  let angle;
  if (Math.hypot(x, y) < 0.3) {
    if (!Number.isFinite(alpha)) return;
    // Near horizontal, gravity cannot distinguish turns around the camera axis.
    flatReference ??= { alpha, angle: deviceAngle ?? screenAngle() };
    angle = flatReference.angle + (alpha - flatReference.alpha) * Math.sign(Math.cos(pitch));
  } else {
    flatReference = undefined;
    angle = Math.atan2(x, y) * 180 / Math.PI;
  }
  if (deviceAngle === undefined || Math.abs((angle - deviceAngle + 540) % 360 - 180) > 55) {
    deviceAngle = Math.round(angle / 90) * 90;
  }
}

function frameRotation(current, width, height, rotation, mirrored) {
  const display = screenAngle();
  const portrait = height > width;
  const direction = current.frontCamera ? 1 : -1;
  if (!current.reference) {
    current.reference = { display, physical: deviceAngle, portrait, rotation, mirrored };
    current.size = portrait ? [480, 640] : [640, 480];
  }
  const reference = current.reference;
  const displayTurn = display - reference.display;
  if (reference.physical === undefined && deviceAngle !== undefined) {
    reference.physical = deviceAngle - displayTurn;
  }
  const physicalTurn = reference.physical === undefined ? displayTurn : deviceAngle - reference.physical;
  // Compare each frame to the first rather than accumulating changes between shutters.
  const reportedTurn = rotation === undefined || reference.rotation === undefined ? 0 : rotation - reference.rotation;
  const swapped = portrait !== reference.portrait;
  if (reference.physical === undefined && displayTurn === 0) return 0;
  const swappedTurn = Math.abs(displayTurn) % 180 === 90 ? displayTurn : physicalTurn;
  const applied = reportedTurn || (swapped ? direction * swappedTurn : 0);
  return (direction * physicalTurn - applied) * (current.reference.mirrored ? -1 : 1) % 360;
}

function drawCameraImage(context, current) {
  let frame;
  try {
    if ('rotation' in (window.VideoFrame?.prototype ?? {})) frame = new VideoFrame(video);
  } catch {
    // Some browsers can display a live stream but cannot wrap it in VideoFrame.
  }
  try {
    const width = frame?.displayWidth ?? video.videoWidth;
    const height = frame?.displayHeight ?? video.videoHeight;
    if (!width || !height) throw new Error('The camera image is unavailable.');
    const mirrored = frame?.flip ?? current.reference?.mirrored ?? false;
    const angle = frameRotation(current, width, height, frame?.rotation, mirrored);
    const [outputWidth, outputHeight] = current.size;
    const quarterTurn = Math.abs(angle) % 180 === 90;
    const scale = Math.min(outputWidth / (quarterTurn ? height : width),
      outputHeight / (quarterTurn ? width : height));
    context.canvas.width = outputWidth;
    context.canvas.height = outputHeight;
    context.fillStyle = '#000';
    context.fillRect(0, 0, outputWidth, outputHeight);
    context.save();
    context.translate(outputWidth / 2, outputHeight / 2);
    context.rotate(angle * Math.PI / 180);
    if (mirrored !== current.reference.mirrored) context.scale(-1, 1);
    context.drawImage(frame ?? video, -width * scale / 2, -height * scale / 2, width * scale, height * scale);
    context.restore();
  } finally {
    frame?.close();
  }
}

async function drawFrame(current, now, takenAt, index) {
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');
  drawCameraImage(context, current);
  const time = captureTime(takenAt);
  const text = `${index}  ${Math.round((now - current.started) / 1000)} s  ${time.label}`;
  context.font = 'bold 14px system-ui, sans-serif';
  context.textBaseline = 'middle';
  const labelWidth = Math.ceil(context.measureText(text).width) + 12;
  const left = canvas.width - labelWidth - 6;
  context.fillStyle = '#124f9e';
  context.fillRect(left, 6, labelWidth, 24);
  context.fillStyle = '#fff';
  context.fillText(text, left + 6, 18);
  const jpeg = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.9));
  return addCaptureExif(jpeg, time, canvas.width, canvas.height);
}

function capture(current, now) {
  const index = current.frames.length;
  const frame = drawFrame(current, now, new Date(), index).catch(() => false);
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
    if (cameraReady()) {
      capture(current, now);
      $('status').textContent = '';
    } else {
      $('status').textContent = 'Camera temporarily unavailable. Waiting for the next shutter.';
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
    frontCamera: stream?.getVideoTracks()[0]?.getSettings().facingMode === 'user',
    frames: [],
  };
  session = current;
  try {
    if (!audio && window.AudioContext) audio = new AudioContext();
    if (audio && audio.state !== 'running') current.audioReady = audio.resume().catch(() => {});
  } catch {
    // The preview and capture can continue when browser audio is unavailable.
  }
  showScreen('starting');
  startCountdown.textContent = START_DELAY_MS / 1000;
  $('cancel-start').focus({ preventScroll: true });
  holdScreenAwake(current);
  current.startAt = performance.now() + START_DELAY_MS;
  tickStartCountdown(current);
}

function tickStartCountdown(current) {
  if (document.hidden) {
    cancelStart('Countdown canceled when the camera went into the background.');
    return;
  }
  const remaining = current.startAt - performance.now();
  if (remaining <= 0) {
    if (cameraReady()) {
      startRecording(current);
    } else if (remaining > -2000) {
      startCountdown.textContent = '1';
      current.timer = setTimeout(() => tickStartCountdown(current), TICK_MS);
    } else {
      cancelStart('The camera is unavailable. Wait for the preview to resume before starting.');
    }
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
  current.started = performance.now();
  current.nextAt = current.started;
  current.endsAt = current.started + current.duration;
  current.abortAt = current.started + ABORT_WINDOW_MS;
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

function cancelStart(reason = '') {
  if (screen !== 'starting') return;
  releaseCaptureResources(session);
  session = undefined;
  showScreen('setup');
  $('status').textContent = reason;
  startButton.focus({ preventScroll: true });
}

function stopRecording(current) {
  releaseCaptureResources(current);
  flashAnimation?.cancel();
  releasePreview();
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
  $('status').textContent = [reason, count < results.length ? 'Some JPEGs could not be encoded with verified EXIF.' : '']
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
window.addEventListener('deviceorientation', readDeviceAngle);
if (window.DeviceOrientationEvent?.requestPermission) {
  motionButton.hidden = false;
  motionButton.addEventListener('click', async () => {
    motionButton.disabled = true;
    try {
      if (await DeviceOrientationEvent.requestPermission() === 'granted') {
        motionButton.hidden = true;
        return;
      }
    } catch {
      // Screen orientation is still available when motion access is declined.
    } finally {
      motionButton.disabled = false;
    }
    if (screen === 'setup') $('status').textContent = 'Motion access is off. Using screen orientation.';
  });
}
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) return;
  cancelStart('Countdown canceled when the camera went into the background.');
  finish('Recording ended when the camera went into the background.');
});

openPreview();
