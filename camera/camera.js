/*
 * PlantTracer time lapse camera.
 * (C) 2025 Simson L. Garfinkel.
 */

const UPLOAD_INTERVAL_SECONDS = 5;
const UPLOAD_TIMEOUT_SECONDS = 60;
var  frames_uploaded = 0;
var  debug = false;
const VIDEO_MEDIA_WITH_CONSTRAINTS = {
    video: {
        width: { ideal: 640 },
        height: { ideal: 480 }
    }
};


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

function post_image_to_screen(image) {
    const url = URL.createObjectURL(image);
    const img = document.createElement("img");
    img.src = url;
    img.style.width = "320px";
    document.body.appendChild(img);
}


function playTone(frequency = 440, duration = 0.2) {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = "sine";                     // waveform: sine, square, triangle, sawtooth
    osc.frequency.value = frequency;       // Hz, e.g. 440 = A4
    gain.gain.value = 0.1;                 // volume (0.0–1.0)

    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + duration);  // stop after N seconds
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

async function run_camera() {
    const run_button = document.getElementById('run-button');
    const stop_button = document.getElementById('stop-button');
    const debug_button = document.getElementById('stop-button');

    // Check if the browser supports media devices
    console.log("run_camera...");
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        alert("Your browser does not support camera access.");
        return;
    }

    try {
        // Access the camera
        const stream = await navigator.mediaDevices.getUserMedia(VIDEO_MEDIA_WITH_CONSTRAINTS);
        const track = stream.getVideoTracks()[0];
        const settings = track.getSettings();
        console.log(`Camera started. Actual resolution: ${settings.width}x${settings.height}`);

        // Create a video element to display the stream
        const video = document.createElement("video");
        document.body.appendChild(video);
        video.srcObject = stream;
        await video.play();     // waits for video play to start

        // Create a canvas to display the image
        const canvas = document.createElement("canvas");
        const context = canvas.getContext("2d");

        run_button.disabled = true;
        debug_button.disabled = true;
        stop_button.disabled = false;

        const canvasToBlob = (c, type, q) => new Promise(res => c.toBlob(res, type, q));
        async function captureAndSend() {
            playTone(880, 0.1);  // short, higher-pitch beep
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            context.drawImage(video, 0, 0, canvas.width, canvas.height);

            const blob = await canvasToBlob(canvas, "image/jpeg", 0.95);

            if (debug) {
                post_image_to_console(blob);
                return;
            }

            await post_image(blob);  // or just post_image(blob) if it’s sync
        }

        // lock to prevent overlapping runs
        let busy = false;

        const intervalId = setInterval(async () => {
            if (busy) return;
            busy = true;
            try {
                await captureAndSend();  // safe even if async
            } finally {
                busy = false;
            }
        }, UPLOAD_INTERVAL_SECONDS * 1000);


        // Stop camera when stop_button clicked
        stop_button.addEventListener("click", () => {
            console.log("Stopping camera...");
            clearInterval(intervalId);
            stream.getTracks().forEach(t => t.stop());  // stop all tracks
            video.pause();
            video.srcObject = null;
            run_button.disabled = false;
            stop_button.disabled = true;
            debug_button.disabled = true;
        });
    } catch (error) {
        console.error("Error accessing camera:", error);
    }
};

document.addEventListener('DOMContentLoaded', () => {
    console.log("camera ready function running.");
    document.getElementById('run-button').addEventListener('click',run_camera);
    document.getElementById('debug-button').addEventListener('click', () => { debug=true; run_camera()});
});
