"use strict";
/* jshint esversion: 8 */
/* global alert,document,MediaStreamTrackProcessor,console,createImageBitmap,window,HTMLVideoElement */
// Video player
// https://developer.mozilla.org/en-US/docs/Web/HTML/Element/video#events
// https://developer.mozilla.org/en-US/docs/Web/API/HTMLVideoElement/requestVideoFrameCallback


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
        this.rcb = null;
        this.cache = new LRU(100);
        this.video = document.querySelector("video");
        this.canvas = document.querySelector("canvas");
        this.ctx = this.canvas.getContext("2d");
        this.videoFrame = 0;
        this.requestedFrame = 0;
        this.video.muted = true;
        this.currentFrame = null;
        this.displayedFrame = null;
        this.annotator = null;

        // callback for the requestVideoFrameCallback when loading
        // must be a const so that we can remove the event listener
        this.loadeddata_callback = () => {
            this.video.removeEventListener('loadeddata', this.loadeddata_callback); // don't call a second time
            this.video.pause();
            this.videoFrame = 0;
            this.captureFrame(true);
        };
        this.video.addEventListener('loadeddata', this.loadeddata_callback);
        // play callback takes too much time!
        //this.play_callback = () => {
        //    //this.video.removeEventListener('play', this.play_callback); // don't call a second time
        //    console.log("play_callback this.rcb=",this.rcb);
        //};
        //this.video.addEventListener('play', this.play_callback);
    }
    // Capture and cache the frame and optinally draw the bitmap
    captureFrame(draw) {
        createImageBitmap(this.video).then( (bitmap) => {
            this.cache.set(this.videoFrame, bitmap);
            if (draw) {
                this.ctx.drawImage(bitmap, 0, 0, this.canvas.width, this.canvas.height);
                this.displayedFrame = this.videoFrame;
                if (this.annotator) this.annotator(this.canvas, this.ctx, this.displayedFrame);
            }
        });
    }
    // callback for the requestVideoFrameCallback when running...
    run_callback(now, metadata) {
        this.rcb = null;
        console.log("run_callback videoFrame=",this.videoFrame,"now=",now,"diff=",now-metadata.expectedDisplayTime,"metadata=",metadata);
        this.videoFrame ++;
        if (this.videoFrame == this.requestedFrame) {
            console.log("current frame is requested frame. Capture");
            this.video.pause();
            this.captureFrame(true);
        } else {
            console.log("current frame is not requested frame. Carry on");
            this.rcb = this.video.requestVideoFrameCallback((a,b) => {this.run_callback(a,b);} );
        }
        console.log("run_allback finished. videoFrame=",this.videoFrame);
    }
    // callback for load when reset button is pressed
    load_callback(now, metadata) {
        this.rcb = null;
        this.videoFrame = 0;
        this.video.pause();
        this.captureFrame(true);
    }

    // callback for the requestVideoFrameCallback when loading
    load_run_callback(now, metadata) {
        this.rcb = this.video.requestVideoFrameCallback((a,b) => {this.run_callback(a,b);} );
        this.videoFrame = 0;
        this.video.play();
    }

    load(url) {
        this.video.src = "./tracked.mp4";
        this.video.play();               // can we do this

        const incache = () => {
            let b = this.cache.get(this.requestedFrame);
            if (b) {
                this.ctx.drawImage(b, 0, 0, this.canvas.width, this.canvas.height);
                this.displayedFrame = this.requestedFrame;
                if (this.annotator) this.annotator(this.canvas, this.ctx, this.displayedFrame);
                return true;
            }
            return false;
        };


        document.querySelector('#step').addEventListener('click', (e) => {
            this.requestedFrame = this.displayedFrame + 1;
            if (incache()) return;
            console.log("step click. videoFrame=",this.videoFrame,"requestedFrame=",this.requestedFrame);
            this.rcb = this.video.requestVideoFrameCallback((a,b) => {this.run_callback(a,b);} );
            this.video.play();
        });
        document.querySelector('#back').addEventListener('click', (e) => {
            console.log("step click");
            this.requestedFrame = this.displayedFrame>0 ? this.displayedFrame - 1 : 0;
            if (incache()) return;

            // If the requested frame is in the cache
            // jump to the beginning and run to the requested frame

            this.rcb = this.video.requestVideoFrameCallback((a,b) => {this.load_run_callback(a,b);} );
            console.log("Reloading and seeking to ",this.requestedFrame);
            this.video.src = "./tracked.mp4";
        });
        document.querySelector('#reset').addEventListener('click', (e) => {
            this.rcb = this.video.requestVideoFrameCallback((a,b) => {this.load_callback(a,b);} );
            this.requestedFrame = 0;
            this.video.src = "./tracked.mp4";
        });
    }
}

var ms = new MovieStepper();
const annotate = (canvas,ctx,frame) => {
    console.log("ANNOTATE",canvas,ctx,frame);
    ctx.save();
    ctx.fillStyle = "red";
    ctx.font = '18px sanserif';
    ctx.fillText( `frame ${frame}`, 10, 50, 60);
    ctx.restore();
};
// ms.annotator  = annotate;
const startDrawing = () => { ms.load("./tracked.mp4"); };
window.addEventListener('load', startDrawing);
