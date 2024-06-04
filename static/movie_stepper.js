"use strict";
/* jshint esversion: 8 */
/* global alert,document,MediaStreamTrackProcessor,console */
// code for /analyze

// https://stackoverflow.com/questions/996505/lru-cache-implementation-in-javascript
class LRU {
    constructor(max = 10) {
        this.max = max;
        this.cache = new Map();
    }

    get(key) {
        let item = this.cache.get(key);
        if (item !== undefined) {
            // refresh key
            this.cache.delete(key);
            this.cache.set(key, item);
        }
        return item;
    }

    set(key, val) {
        // refresh key
        if (this.cache.has(key)) this.cache.delete(key);
        // evict oldest
        else if (this.cache.size === this.max) this.cache.delete(this.first());
        this.cache.set(key, val);
    }

    first() {
        return this.cache.keys().next().value;
    }
}


class MovieStepper {
    constructor() {
        this.cache = new LRU();
        this.reader = null;
        this.videoProcessor = null;
        this.currentFrameIndex = null;
        this.video = document.createElement('video');
        this.video.muted = true; // Allow autoplay
        this.video.preload = 'none';

        if (!('MediaStreamTrackProcessor' in window)) {
            alert('MediaStreamTrackProcessor is not supported in this browser.');
            return;
        }

        if (!("requestVideoFrameCallback" in HTMLVideoElement.prototype)) {
            alert('requestVideoFrameCallback is not supported in this browser.');
            return;
        }

        if (!('captureStream' in this.video)) {
            alert("video does not support captureStream()");
            return;
        }
    }

    // See: https://developer.chrome.com/blog/play-request-was-interrupted
    async load(url) {
        this.currentFrameIndex = 0;
        this.url = url;
        this.video.src = url;
        console.log("play ",url);
        var playPromise = this.video.play();
        if (playPromise !== undefined) {
            playPromise.then(_ => {
                // Automatic playback started!
                // Show playing UI.
                // We can now safely pause video...
                video.pause();
            }).catch(error => {
                // Auto-play was prevented
                // Show paused UI.
                console.log("play error:",error);
                alert("play error: ",error);
            });
        }



        // advance to frame 0 and
        //this.video.requestVideoFrameCallback( (now,metadata) => {
        //    console.log("pausing movie now=",now,"metdata=",metadata);
        //   this.video.pause();      // pause immediately to control frame advance
        //});
        const videoTrack = this.video.captureStream().getVideoTracks()[0];
        console.log('videoTrack=',videoTrack);
        this.videoProcessor = new MediaStreamTrackProcessor(videoTrack);
        this.reader = this.videoProcessor.readable.getReader();
    }

    async getFrame(n) {
        if (!this.reader) {
            throw new Error("Video not loaded or processor not initialized.");
        }

        let item = this.cache.get(n);
        if (item) return item;

        // If requesting a previous frame, reset to start
        if (n < this.currentFrameIndex) {
            await this.load(this.url); // Reload the video to reset the reader; fastSeek() is not available.
        }

        // Read frames until reaching the desired frame
        while (this.currentFrameIndex <= n) {
            // Is it this frame?
            const { done, value } = await this.reader.read(); // read the frame
            if (done) {
                throw new Error("Reached end of video before reaching frame " + n);
            }
            if (this.currentFrameIndex === n) {
                const bitmap = await createImageBitmap(value);
                value.close();             // Ensure the frame is closed after processing
                this.cache.set(n, bitmap); // store the results
                return bitmap;
            }
            value.close(); // Close the frame we are skipping

            // advance a single frame
            this.video.requestVideoFrameCallback( (now,metadata) => {
                console.log("2. pausing movie now=",now,"metdata=",metadata);
                this.currentFrameIndex++;
                this.video.pause(); // pause immediately to control frame advance
            });
            await this.video.play(); // gets the next frame
        }
    }
}

export { MovieStepper };
