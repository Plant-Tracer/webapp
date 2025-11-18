"use strict";
/* jshint esversion: 8 */
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
        this.video = document.createElement('video');
        this.video.muted = true; // Allow autoplay
        this.video.preload = 'none';
        this.reader = null;
        //this.videoProcessor = null;
        this.currentFrameIndex = null;

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
        this.currentFrameIndex = null;
        this.url = url;
        this.video.src = url;
        console.log("play ",url);
        this.video.requestVideoFrameCallback( (now, metadata) => {
            this.currentFrameIndex = 0;
            this.video.pause();
            console.log(`now=${now} metadata=${metadata} pause 1`);
        });
    }

    async getFrame(n) {
        // First check to see if it is in the cache
        let item = this.cache.get(n);
        if (item) return item;

        // If requesting a previous frame, reset to start; we can only advance forward.
        if (n < this.currentFrameIndex) {
            await this.load(this.url); // Reload the video to reset the reader; fastSeek() is not available.
        }

        // Read frames one-by-one until reaching the desired frame
        while (this.currentFrameIndex <= n) {
            if (this.currentFrameIndex === n) {
                const bitmap = await createImageBitmap(this.video);
                this.cache.set(n, bitmap); // store the results
                return bitmap;
            }

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
