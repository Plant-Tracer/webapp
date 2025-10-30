/*
 * PlantTracer time lapse camera.
 * (C) 2025 Simson L. Garfinkel.
 */

const UPLOAD_INTERVAL_SECONDS = 5;
const UPLOAD_TIMEOUT_SECONDS = 60;
var  frames_uploaded = 0;

const VIDEO_MEDIA_WITH_CONSTRAINTS = {
    video: {
        width: { ideal: 640 },
        height: { ideal: 480 }
    }
};


console.log("TODO - compute the correct URL")

function setStatus(msg) {
    document.getElementById('status-message').textContent = msg;
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
                setStatus(`Error uploading image status=${uploadResponse.status} ${uploadResponse.statusText}`);
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

    // Check if the browser supports media devices
    console.log("run_camera...");
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        alert("Your browser does not support camera access.");
        return;
    }

    try {
        // Access the camera
        const stream = await navigator.mediaDevices.getUserMedia( VIDEO_MEDIA_WITH_CONSTRAINTS );
        const track = stream.getVideoTracks()[0];
        const settings = track.getSettings();
        console.log(`Camera started. Actual resolution: ${settings.width}x${settings.height}`);

        // Create a video element to display the stream
        const video = document.createElement("video");
        document.body.appendChild(video);
        video.srcObject = stream;
        await video.play();     // waits for video play to start

        // The camera is now running live.
        // Create a canvas to display the image
        const canvas = document.createElement("canvas");
        const context = canvas.getContext("2d");

        run_button.disabled = true;
        stop_button.disabled = false;

        // Function to capture and send an image
        const captureAndSend = async () => {

            // Set canvas size to match video size
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;

            // Draw the current video frame to the canvas
            context.drawImage(video, 0, 0, canvas.width, canvas.height);

            // Convert the canvas to a data URL
            canvas.toBlob(post_image, "image/jpeg", 0.95);
        };

        // Capture and send an image every UPLOAD_INTERVAL_SECONDS seconds
        setInterval(captureAndSend, UPLOAD_INTERVAL_SECONDS * 1000);
    } catch (error) {
        console.error("Error accessing camera:", error);
    }
};

document.addEventListener('DOMContentLoaded', () => {
    console.log("camera ready function running.");
    document.getElementById('run-button').addEventListener('click',run_camera);
});
