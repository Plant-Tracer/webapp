"use strict";
/*jshint esversion: 8 */
/*global $*/

/**
 * Canvas Movie Controller:
 * Holds all of the frames for a movie and changes the image and annotation in response to button press or timer
 */


const PLAY_MSEC = 1000;          // pause between frames; could be 1000/29.92

import { CanvasController, CanvasItem, Marker, WebImage } from "./canvas_controller.js";

class MovieController extends CanvasController {
    constructor( div_selector ) {
        super( div_selector + " canvas ", div_selector + " .zoom" );
        div_selector += ' ';    // make sure there is a trailing space
        this.div_selector = div_selector;

        // Movie state variables
        this.frame_number_field = $(div_selector + " .frame_number_field");
        this.frame_number = null;  // no frame number to start
        this.playing = 0;   // are we playing a movie? +1 means forward, -1 is reverse
        this.frames = [];         // needs to be set with load_movie
        this.cached_web_images = [];
        this.timer = null;          // when playing or reverse playing, this is the timer that repeatedly calls next or prev
        this.bounce = false;    // when playing, bounce off the ends
        this.loop = false;    // when playing, Loop from end to beginning

        // set up movie controls  (manipulations are all done with CSS classes)
        $(div_selector + " input.first_button").on('click', (_) => {this.goto_frame(0);});
        $(div_selector + " input.play_reverse").on('click', (_) => {this.play(-1);});
        $(div_selector + " input.play_forward").on('click',   (_) => {this.play(+1);});
        $(div_selector + " input.pause_button").on('click', (_) => {this.stop_button_pressed();});
        $(div_selector + " input.last_button").on('click', (_) => {this.goto_frame(1e10);});
        $(div_selector + " input.next_frame").on('click',  (_) => {this.goto_frame(this.frame_number+1);});
        $(div_selector + " input.prev_frame").on('click',  (_) => {this.goto_frame(this.frame_number-1);});
        $(div_selector + " input.frame_number_field").on('input', (_) => {
            let new_frame = this.frame_number_field[0].value;
            if (new_frame=='') {            // turn '' into a "0"
                this.frame_number_field[0].value='0';
                this.frame_number = 0;
            }
            // remove leading 0 from two-digit numbers
            if (new_frame.length == 2 && new_frame[0]=='0') {
                new_frame = new_frame[1];
                this.frame_number_field[0].value=new_frame;
            }
            this.goto_frame( new_frame );
        });
    }

    set_bounce( bounce) { this.bounce = bounce; }
    set_loop( loop) { this.loop = loop; }

    /*
     * loads the description of the movie and annotations
     * `frames` comes from the get-movie-metadata which is called:
     * - when a movie is first loaded (and it is filled if the movie is tracked.)
     * - is called to poll for tracking completion,
     *
     * If a movie is not tracked we do not know how many frames it is.
     * In this case, we:
     * - Use the JPEG URL for the first frame
     * - Set up the default trackpoints and write them to the server.
     * - Wait for the user to move the trackpoints and then click 'track',
     *   which will track and then gets the frames array.
     */
    load_movie( frames ){
        // frames is an array with [nn] frame number indexes.
        // frames[0] is the first element.
        // frames[0].frame_url - the URL of the first frame
        // frames[0].markers[] - an array of marker objects
        console.log("load_movie(frames)=",frames);
        this.frames = frames;

        /* Now preload all of the images, downloading new ones as necessary.
         * Typically load_movie is called repeatedly for each new tracking,
         * but the images are only downloaded the first time.
         */
        for(let i = 0;i<this.frames.length;i++){
            if (!this.cached_web_images[i]) {
                this.cached_web_images[i] = new WebImage(0, 0, frames[i].frame_url);
            }
            this.frames[i].web_image = this.cached_web_images[i];
        }
        $(this.div_selector + " span.total-frames").text(this.total_frames);
        if (!this.frame_number) { // if frame number is not set, be sure we move to frame 0
            this.goto_frame(0);
        }
        this.redraw();
    }

    /**
     * Change the frame. This is called repeatedly when the movie is
     * playing, with the frame number changing First we verify the
     * next frame number, then we call the /api/get-frame call to get
     * the frame, with get_frame_handler getting the data.
     *
     */
    goto_frame( frame ) {
        console.log(`goto_frame(${frame})`);

        frame = parseInt(frame);         // make sure it is integer
        if ( isNaN(frame) || frame<0 ) {
            frame = 0;
        }

        if (frame>=this.frames.length) {
            frame = this.frames.length-1;
        }

        if (frame==this.frame_number && !(frame===null)) {
            return;             // did not change
        }

        // set the frame number, clear the screen and re-add the objects
        this.frame_number = frame;
        this.clear_objects();
        this.add_object( this.frames[frame].web_image ); // always add this first
        this.add_frame_objects( frame );                 // typically will be subclassed
        $(this.div_selector+" input.frame_number_field").val(this.frame_number);
        this.set_movie_control_buttons();     // enable or disable buttons as appropriate
        this.redraw();
    }

    // override this in your subclass to add things that annotate the movie.
    add_frame_objects( frame ){
    }

    /** play is using for playing (delta=+1) and reversing (delta=-1).
     * It's called by the timer or when the button is pressed
     */
    play(delta) {
        console.log("play delta=",delta,"frame:",this.frame_number);

        var next_frame = this.frame_number;
        var next_delta = delta;
        if (this.timer) {
            clearTimeout(this.timer);
            this.timer = null;
        }
        this.playing = delta;
        if (delta>0) {
            if (this.frame_number >= this.frames.length-1) {
                if (this.loop) {
                    next_frame = 0;
                } else if (this.bounce) {
                    next_frame = this.frames.length - 2;
                    next_delta = -1;
                } else {
                    this.playing=0;
                }
            } else {
                next_frame += delta;
            }
        }
        if (delta<0) {
            if (this.frame_number == 0) {
                if (this.loop) {
                    next_frame = this.frames.length-1;
                } else if (this.bounce) {
                    next_frame = 1;
                    next_delta = 1;
                } else {
                    this.playing = 0;
                }
            } else {
                next_frame += delta;
            }
        }
        if (this.playing) {
            this.goto_frame(next_frame);
            this.timer = setTimeout( () => {this.timer=null;this.play(next_delta);}, PLAY_MSEC );
        }
        this.set_movie_control_buttons();     // enable or disable buttons as appropriate
    }

    stop_button_pressed() {
        if (this.timer) {
            clearTimeout(this.timer);
            this.timer = null;
        }
        this.playing = false;
        this.set_movie_control_buttons();     // enable or disable buttons as appropriate
    }


    /**
     * enable or disable controls as appropriate.
     */
    set_movie_control_buttons() {
        // no frames, nothing is enabled
        if (this.frames.length==0){
            $(this.div_selector + ' input.frame_movement').prop('disabled',true);
            $(this.div_selector + ' input.frame_stoppage').prop('disabled',true);
            $(this.div_selector + ' input.play_forward').prop('disabled',true);
            $(this.div_selector + ' input.play_reverse').prop('disabled',true);
            return;
        }
        // if playing, everything but 'stop' and reversing direciton is disabled
        if (this.playing) {
            $(this.div_selector + ' input.frame_movement').prop('disabled',true);
            $(this.div_selector + ' input.frame_stoppage').prop('disabled',false);
            $(this.div_selector + ' input.play_forward').prop('disabled', this.playing>0);
            $(this.div_selector + ' input.play_reverse').prop('disabled',this.playing<0);
            return;
        }
        // movie not playing

        $(this.div_selector + ' input.frame_number_field').prop('disabled',false);
        $(this.div_selector + ' input.frame_stoppage').prop('disabled',true);
        $(this.div_selector + ' input.movement_backwards').prop('disabled', this.frame_number==0); // can't move backwards
        $(this.div_selector + ' input.movement_forwards').prop('disabled', this.frame_number==this.length-1);
        $(this.div_selector + ' input.play_forward').prop('disabled', this.frame_number==this.length-1);
        $(this.div_selector + ' input.play_reverse').prop('disabled', this.frame_number==0);
    }
}

export { MovieController };
