const startDrawing = () => {
    const button = document.querySelector("button");
    const video = document.querySelector("video");
    const canvas = document.querySelector("canvas");
    const ctx = canvas.getContext("2d");
    const fpsInfo = document.querySelector("#fps-info");
    const metadataInfo =  document.querySelector("#metadata-info");

    button.addEventListener('click', () => video.paused ? video.play() : video.pause());

    video.addEventListener('play', () => {
        if (!('requestVideoFrameCallback' in HTMLVideoElement.prototype)) {
            return alert('Your browser does not support the `Video.requestVideoFrameCallback()` API.');
        }
    });

    let paintCount = 0;
    let startTime = 0.0;

    const updateCanvas = (now, metadata) => {
        video.pause();
        console.log("now=",now,"metadata=",metadata);
        if (startTime === 0.0) {
	    startTime = now;
        }

        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

        const elapsed = (now - startTime) / 1000.0;
        const fps = (++paintCount / elapsed).toFixed(3);
        fpsInfo.innerText = !isFinite(fps) ? 0 : fps;
        metadataInfo.innerText = JSON.stringify(metadata, null, 2);
        video.requestVideoFrameCallback(updateCanvas);
    };

    video.src = "./tracked.mp4";
    video.muted = true;
    video.requestVideoFrameCallback(updateCanvas);

    video.play();               // can we do this

};

window.addEventListener('load', startDrawing);
