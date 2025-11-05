/*
 * PlantTracer time lapse camera.
 * (C) 2025 Simson L. Garfinkel, with lots of help from ChatGPT
 */

const UPLOAD_INTERVAL_SECONDS = 5;
const UPLOAD_TIMEOUT_SECONDS = 60;
let  frames_uploaded = 0;
let  debug = false;
let __runController = null;

const VIDEO_MEDIA_WITH_CONSTRAINTS = {
    video: {
        width: { ideal: 640 },
        height: { ideal: 480 }
    }
};


function computeFit(srcW, srcH, dstW, dstH) {
    const s = Math.min(dstW / srcW, dstH / srcH);
    const dw = Math.round(srcW * s);
    const dh = Math.round(srcH * s);
    const dx = Math.floor((dstW - dw) / 2);
    const dy = Math.floor((dstH - dh) / 2);
    return { dx, dy, dw, dh };
}

function formatTimestamp() {
    const now = new Date();
    const dateStr = now.toLocaleDateString([], { year: 'numeric', month: '2-digit', day: '2-digit' });
    const timeStr = now.toLocaleTimeString([], { hour12: false });
    return `${dateStr} ${timeStr}`;
}


// Portrait detection for auto-rotate (source aspect, not CSS)
function isPortrait(video) {
    const vw = video.videoWidth || 640;
    const vh = video.videoHeight || 480;
    return vh > vw;
}

function setStatus(msg) {
    document.getElementById('status-message').textContent = msg;
}

function post_image_to_console(blob) {
    const reader = new FileReader();
    reader.onload = () => {
        const dataUrl = reader.result; // "data:image/jpeg;base64,..." etc.
        const style = [
            "display:inline-block",
            "line-height:0",
            "padding:80px 120px",          // box size
            `background:url("${dataUrl}") center / contain no-repeat`,
            "border:1px solid #999",
        ].join(";");

        console.log("%c ", style);
    };
    reader.readAsDataURL(blob);
}

// (unused) post_image_to_screen is dead code now; kept for debugging convenience.
function post_image_to_screen(image) {
    const url = URL.createObjectURL(image);
    const img = document.createElement("img");
    img.src = url;
    img.style.width = "320px";
    document.body.appendChild(img);
}


// Reuse a single AudioContext to avoid exceeding browser limits
const __audioCtx = new (window.AudioContext || window.webkitAudioContext)();
function playTone(frequency = 440, duration = 1.0) {
    const osc = __audioCtx.createOscillator();
    const gain =__audioCtx.createGain();

    osc.type = "sine";                     // waveform: sine, square, triangle, sawtooth
    osc.frequency.value = frequency;       // Hz, e.g. 440 = A4
    gain.gain.value = 0.1;                 // volume (0.0–1.0)

    osc.connect(gain).connect(__audioCtx.destination);
    const t0 = __audioCtx.currentTime;
    osc.start(t0);
    osc.stop(t0 + duration);  // stop after N seconds
}


/* post_image:
 * 1. contact the server for the signed POST parameters.
 * 2. Using the signed post, upload to AWS S3.
 */
function post_image(image) {
    console.log("post_image",image);
    let formData = new FormData();
    formData.append("api_key", document.getElementById('api_key').textContent);
    fetch('api/post-image', { method: "POST", body: formData })
        .then(r => {
            if (!r.ok) {
                setStatus(`Error: ${r.status} ${r.statusText}`);
                throw new Error(`Failed to get signed upload URL: ${r.statusText}`);
            }
            return r.json();    // returned to next .then()
        })
        .then(obj => {
	    if (obj.error) {
                throw { message: obj.error };
	    }
            frames_uploaded += 1;
            setStatus(`Uploading frame ${frames_uploaded}.`);

            // Now use the presigned_post to upload to s3
            const uploadFormData = new FormData();
            for (const field in obj.presigned_post.fields) {
                uploadFormData.append(field, obj.presigned_post.fields[field]);
            }
            uploadFormData.append("file", image); // finally append the image; note that order matters.

            // Use an AbortController for the timeout:
            // https://developer.mozilla.org/en-US/docs/Web/API/AbortController
            const ctrl = new AbortController();
            setTimeout(() => ctrl.abort(), UPLOAD_TIMEOUT_SECONDS * 1000);
            return fetch(obj.presigned_post.url, {
                method: "POST",
                body: uploadFormData,
                signal: ctrl.signal
            });
        })
        .then(uploadResponse => {
            if (!uploadResponse.ok) {
                throw new Error(`Upload failed: ${uploadResponse.statusText}`);
            }
            setStatus(`Image ${frames_uploaded} uploaded.`);
        })
        .catch(error => {
            if (error.name === 'AbortError') {
                setStatus(`Timeout (${UPLOAD_TIMEOUT_SECONDS}s) uploading image.`);
            } else {
                setStatus(`An error occurred: ${error.message}`);
            }
        });
}

async function captureAndSend(video, totalSeconds, post_image, debug = false) {
    // Output size based on orientation
    const portrait = isPortrait(video);
    const OUT_W = portrait ? 480 : 640;
    const OUT_H = portrait ? 640 : 480;

    // Off-screen canvas
    const cap = document.createElement("canvas");
    cap.width = OUT_W;
    cap.height = OUT_H;
    const cctx = cap.getContext("2d");

    // Fit full frame without distortion
    const vw = video.videoWidth  || OUT_W;
    const vh = video.videoHeight || OUT_H;
    const fit = computeFit(vw, vh, OUT_W, OUT_H);

    // Draw video frame
    cctx.clearRect(0, 0, OUT_W, OUT_H);
    cctx.drawImage(video, 0, 0, vw, vh, fit.dx, fit.dy, fit.dw, fit.dh);

    // Draw full white bar + timestamp (same style as overlay, but 100% filled)
    const barH = Math.max(28, Math.round(OUT_H * 0.07));
    const y = OUT_H - barH;

    cctx.fillStyle = "#000";
    cctx.fillRect(0, y, OUT_W, barH);

    cctx.fillStyle = "#fff";
    cctx.fillRect(0, y, OUT_W, barH);

    cctx.font = `${Math.round(barH * 0.55)}px sans-serif`;
    cctx.textBaseline = "middle";
    cctx.fillStyle = "#000";
    cctx.textAlign = "left";
    cctx.fillText(formatTimestamp(), 8, y + barH / 2);

    // Encode
    const blob = await new Promise(res => cap.toBlob(res, "image/jpeg", 0.95));

    // Post or debug
    if (debug) {
        // show in console or DOM — your existing debug helper
        post_image_to_console(blob);
    } else {
        await post_image(blob);
    }
}


async function run_camera() {
    // kill old listeners (if any) before wiring new ones
    if (__runController) {
        __runController.abort();
    }
    __runController = new AbortController();
    const { signal } = __runController;

    // set up buttons
    const run_button = document.getElementById('run-button');
    const stop_button = document.getElementById('stop-button');
    const debug_button = document.getElementById('debug-button');

    // Check if the browser supports media devices
    console.log("run_camera...");
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        alert("Your browser does not support camera access.");
        return;
    }

    try {
        // Access the camera
        const stream = await navigator.mediaDevices.getUserMedia(VIDEO_MEDIA_WITH_CONSTRAINTS);
        const { container, video, overlay, octx, resizeOverlay } = setupLiveView(stream);
        await video.play(); // ensure dimensions become available

        const track = stream.getVideoTracks()[0];
        const settings = track.getSettings();
        console.log(`Camera started. Actual resolution: ${settings.width}x${settings.height}`);
        await video.play();     // waits for video play to start

        const viewCanvas = document.createElement("canvas");           // shows scaled, full frame
        const viewCtx = viewCanvas.getContext("2d");
        // Make the canvas actually cover the viewport (CSS pixels)
        Object.assign(viewCanvas.style, {
            position: "fixed",
            inset: "0",
            width: "100vw",
            height: "100vh",
            display: "block",
            pointerEvents: "none",
            background: "black",  // optional; avoids flash
        });
        document.body.appendChild(viewCanvas);

        const captureCanvas = document.createElement("canvas");        // offscreen for upload
        const captureCtx = captureCanvas.getContext("2d");

        run_button.disabled = true;
        debug_button.disabled = true;
        stop_button.disabled = false;

        [run_button, stop_button, debug_button].forEach(el => {
            if (!el) return;
            el.style.position = el.style.position || "relative";
            el.style.zIndex = "1";
        });


        function resizeViewCanvas() {
            const cssW = window.innerWidth;
            const cssH = window.innerHeight;
            const dpr  = window.devicePixelRatio || 1;
            // drawing buffer in device pixels for crispness
            viewCanvas.width  = Math.round(cssW * dpr);
            viewCanvas.height = Math.round(cssH * dpr);
            // scale context so we can draw in CSS pixel units below
            viewCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
        }
        resizeViewCanvas();

        function setupLiveView(stream) {
            // Container
            const container = document.createElement("div");
            Object.assign(container.style, {
                position: "relative",
                width: "100%",
                height: "100%",
                maxWidth: "100vw",
                maxHeight: "100vh",
                background: "black",
                overflow: "hidden",
            });
            document.body.appendChild(container);

            // Live <video>
            const video = document.createElement("video");
            video.srcObject = stream;
            video.playsInline = true;
            video.muted = true;
            video.autoplay = true;
            Object.assign(video.style, {
                position: "absolute",
                inset: "0",
                width: "100%",
                height: "100%",
                objectFit: "contain",   // <-- full image visible, no cropping
                background: "black",
            });
            container.appendChild(video);

            // Transparent overlay canvas for the bar + text
            const overlay = document.createElement("canvas");
            const octx = overlay.getContext("2d");
            Object.assign(overlay.style, {
                position: "absolute",
                inset: "0",
                width: "100%",
                height: "100%",
                pointerEvents: "none",
            });
            container.appendChild(overlay);

            // Size the overlay drawing buffer to match its CSS size * DPR
            function resizeOverlay() {
                const rect = container.getBoundingClientRect();
                const dpr = window.devicePixelRatio || 1;
                overlay.width  = Math.max(1, Math.round(rect.width  * dpr));
                overlay.height = Math.max(1, Math.round(rect.height * dpr));
                // draw in CSS pixels by scaling context
                octx.setTransform(dpr, 0, 0, dpr, 0, 0);
            }

            // Initial sizing
            resizeOverlay();

            return { container, video, overlay, octx, resizeOverlay };
        }

        function drawOverlay(octx, overlay, secondsRemaining, totalSeconds) {
            const W = overlay.width  / (window.devicePixelRatio || 1);
            const H = overlay.height / (window.devicePixelRatio || 1);

            // Clear
            octx.clearRect(0, 0, W, H);

            // Bar geometry
            const barH = Math.max(28, Math.round(H * 0.07));
            const y = H - barH;

            // Background bar (black)
            octx.fillStyle = "#000";
            octx.fillRect(0, y, W, barH);

            // Progress (white)
            const progressed = Math.max(0, Math.min(totalSeconds, totalSeconds - secondsRemaining));
            const frac = totalSeconds ? progressed / totalSeconds : 1;
            octx.fillStyle = "#fff";
            octx.fillRect(0, y, Math.round(W * frac), barH);

            // Text: left = timestamp (black), right = seconds (black)
            const text = formatTimestamp();
            const right = `${Math.max(0, secondsRemaining)}s`;

            octx.font = `${Math.round(barH * 0.55)}px sans-serif`;
            octx.textBaseline = "middle";
            octx.fillStyle = "#000";
            const ty = y + barH / 2;

            octx.textAlign = "left";
            octx.fillText(text, 8, ty);

            octx.textAlign = "right";
            octx.fillText(right, W - 8, ty);
        }




        // Ensure we have real video dimensions before the first paint
        if (!video.videoWidth || !video.videoHeight) {
            await new Promise(r => video.addEventListener("loadedmetadata", r, { once: true }));
        }

        function drawFrame(secondsRemaining) {
            const VIEW_W = window.innerWidth;
            const VIEW_H = window.innerHeight;
            // Draw in CSS pixel coordinates (we scaled the context in resizeViewCanvas)

            const vw = video.videoWidth || 640;
            const vh = video.videoHeight || 480;
            const fit = computeFit(vw, vh, VIEW_W, VIEW_H);

            // Clear + draw full frame, letterboxed
            viewCtx.clearRect(0, 0, VIEW_W, VIEW_H);
            viewCtx.drawImage(video, 0, 0, vw, vh, fit.dx, fit.dy, fit.dw, fit.dh);

            // --- overlay bar (same as before, but on viewCanvas/viewCtx) ---
            const barH = Math.max(28, Math.round(VIEW_H * 0.07));
            const y = VIEW_H - barH;

            // black background bar
            viewCtx.fillStyle = "#000";
            viewCtx.fillRect(0, y, VIEW_W, barH);

            // white progress
            const total = UPLOAD_INTERVAL_SECONDS;
            const progressed = total - secondsRemaining;
            const frac = Math.min(1, Math.max(0, progressed / total));
            viewCtx.fillStyle = "#fff";
            viewCtx.fillRect(0, y, Math.round(VIEW_W * frac), barH);

            // date + time (black text, no shadow)
            const now = new Date();
            const dateStr = now.toLocaleDateString([], { year: 'numeric', month: '2-digit', day: '2-digit' });
            const timeStr = now.toLocaleTimeString([], { hour12: false });
            const leftText = `${dateStr} ${timeStr}`;
            const rightText = `${secondsRemaining}s`;

            viewCtx.font = `${Math.round(barH * 0.55)}px sans-serif`;
            viewCtx.textBaseline = "middle";
            viewCtx.fillStyle = "#000";

            const textY = y + barH / 2;
            viewCtx.textAlign = "left";
            viewCtx.fillText(leftText, 8, textY);

            viewCtx.textAlign = "right";
            viewCtx.fillText(rightText, VIEW_W - 8, textY);
        }

        let busy = false;        // lock to prevent overlapping runs
        let secondsRemaining = UPLOAD_INTERVAL_SECONDS;
        drawFrame(secondsRemaining);                  // initial paint

        const intervalId = setInterval(async () => {
            if (busy) return;
            busy = true;
            try {
                secondsRemaining -= 1;
                if (secondsRemaining > 0) {
                    // update bar only
                    drawOverlay(octx, overlay, secondsRemaining, UPLOAD_INTERVAL_SECONDS);
                    playTone(261.63, 0.05); // quiet tick middle C
                } else {
                    // final: draw full bar and capture
                    playTone(440, 0.50); // quiet tick A
                    await captureAndSend();
                    secondsRemaining = UPLOAD_INTERVAL_SECONDS; // reset cycle
                    drawOverlay(octx, overlay, secondsRemaining, UPLOAD_INTERVAL_SECONDS);
                }
            } finally {
                busy = false;
            }
        }, 1000);

        // Repaint on viewport changes (covers orientation)
        // keep a reference so we can remove it later
        const onResize = () => {
            resizeViewCanvas();
            drawOverlay(octx, overlay, secondsRemaining, UPLOAD_INTERVAL_SECONDS);
        };
        window.addEventListener("resize", onResize, { signal });

        // Stop camera when stop_button clicked
        let stopped = false;
        const onStop = () => {
            if (stopped) return;
            stopped = true;
            console.log("Stopping camera...");
            clearInterval(intervalId);
            stream.getTracks().forEach(t => t.stop());  // stop all tracks
            container.remove();
            video.pause();
            video.srcObject = null;

            // Abort all listeners for this run (resize + this click)
            __runController.abort();
            __runController = null;

            // remove view canvas & video element to avoid leaks
            viewCanvas.remove();
            video.remove();
            // enable buttons
            run_button.disabled = false;
            stop_button.disabled = true;
            debug_button.disabled = true;
        };
        stop_button.addEventListener("click", onStop, { once: true, signal });
    } catch (error) {
        console.error("Error accessing camera:", error);
    }
};

document.addEventListener('DOMContentLoaded', () => {
    console.log("camera ready function running.");
    document.getElementById('run-button').addEventListener('click',run_camera);
    document.getElementById('debug-button').addEventListener('click', () => { debug=true; run_camera()});
});
