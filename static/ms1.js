"use strict";
/* jshint esversion: 8 */
// code for /analyze

class MovieStepper {
    constructor() {      // html_id is where this canvas gets inserted
        this.frames = [];
        if (! 'MediaStreamTrackProcessor' in window) {
            alert('MediaStreamTrackProcessor is not supported in this browser.');
            return;
        }
    }
    async load(url) {
        // Initial implementation reads the entire movie into RAM, all at once

        const video = document.createElement('video');
        video.muted=true;       // allow autoplay
        video.src=url;
        video.play().then(() => {
            if (! 'captureStream' in video) {
                alert("video does not support captureStream()");
                return;
            }

            // Video is playing; grab the frames
            const videoTrack = video.captureStream().getVideoTracks()[0];
            const videoProcessor = new MediaStreamTrackProcessor(videoTrack);
            const reader = videoProcessor.readable.getReader();
            let count=0;

            const readFrame = () => {
                reader.read().then(({ done, value }) => {
                    if (done) {
                        console.log('Reading complete');
                        return;
                    }

                    console.log(`read frame ${count}`);
                    createImageBitmap(value).then(bitmap => {
                        this.frames[count] = bitmap;
                        count++;
                        value.close();
                        readFrame(); // Read the next frame
                    });
                }).catch(error => {
                    console.error(`Error reading frame ${count}:`, error);
                });
            };

            readFrame(); // Start reading frames
        }).catch( error => {
            console.error('Error attempting to play video:', error);
        });
    }
}

export { MovieStepper };
