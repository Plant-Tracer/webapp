const startDrawing = () => {
    //const button = document.querySelector("button");
    const video = document.querySelector("video");
    const canvas = document.querySelector("canvas");
    const ctx = canvas.getContext("2d");
    //const fpsInfo = document.querySelector("#fps-info");
    const metadataInfo =  document.querySelector("#metadata-info");

    //button.addEventListener('click', () => video.paused ? video.play() : video.pause());

    const updateCanvas = (now, metadata) => {
        video.pause();
        console.log("now=",now,"metadata=",metadata);
        createImageBitmap(video).then( (bitmap) => {
            console.log("bitmap=",bitmap);
            ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        });
        //ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

        metadataInfo.innerText = JSON.stringify(metadata, null, 2);
        video.requestVideoFrameCallback(updateCanvas);
    };

    video.src = "./tracked.mp4";
    video.muted = true;
    video.requestVideoFrameCallback(updateCanvas);

    video.play();               // can we do this

};

window.addEventListener('load', startDrawing);
