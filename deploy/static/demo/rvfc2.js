/* global window,$*/


const startDrawing = () => {
    const video = document.querySelector("video");
    const canvas = document.querySelector("canvas");
    const ctx = canvas.getContext("2d");
    const metadataInfo =  document.querySelector("#metadata-info");
    let currentFrame = 0;

    //button.addEventListener('click', () => video.paused ? video.play() : video.pause());

    const captureFrame = (e=null) => {
        video.pause();
        createImageBitmap(video).then( (bitmap) => {
            console.log("bitmap=",bitmap);
            ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        });
    }

    const updateCanvas = (now, metadata) => {
        console.log("currentFrame=",currentFrame,"now=",now,"diff=",now-metadata.expectedDisplayTime,"metadata=",metadata);
        captureFrame();
        metadataInfo.innerText = JSON.stringify(metadata, null, 2);
    };

    video.muted = true;
    video.src = "./tracked.mp4";

    // This is fired when the first frame is loaded. We pause the play and capture the frame

    video.addEventListener('loadeddata', captureFrame);

    video.play();               // can we do this

    document.querySelector('#step').addEventListener('click', (e) => {
        console.log("step click");
        video.requestVideoFrameCallback(updateCanvas);
        currentFrame ++;
        video.play();
    });
    document.querySelector('#back').addEventListener('click', (e) => {
        console.log("step click");
        video.requestVideoFrameCallback(updateCanvas);
        currentFrame ++;
        video.play();
    });
    document.querySelector('#reset').addEventListener('click', (e) => {
        video.removeEventListener('loaddata',captureFrame)
        video.requestVideoFrameCallback(updateCanvas);
        currentFrame = 0;
        video.src = "./tracked.mp4";
    });
};

window.addEventListener('load', startDrawing);
