"use strict";
/* jshint esversion: 8 */
// code for /analyze

/*global api_key */
/*global movie_id */

const PLAY_MSEC = 100;          // pause between frames; could be 1000/29.92

import { CanvasController, CanvasItem, Marker, WebImage } from "./canvas_controller.js";

class MovieController extends CanvasController {
    constructor( div_selector ) {
        console.log("div_selector1=",div_selector);
        super( div_selector + " canvas", div_selector + " .zoom" );
        console.log("div_selector2=",div_selector);
        this.div_selector = div_selector;
        console.log("this.div_selector=",this.div_selector);

        // Movie state variables
        this.frame_number_field = $(div_selector + " .frame_number_field");
        this.frame_number = null;  // no frame number to start
        this.playing = false;   // are we playing a movie?
        this.playing_direction = 1; // -1 for reverse
        this.frames = [];         // needs to be set with load_movie
        this.timer = null;          // when playing or reverse playing, this is the timer that repeatedly calls next or prev

        // set up movie controls  (manipulations are all done with CSS classes)
        $(div_selector + " .first_button").on('click', (_) => {this.goto_frame(0);});
        $(div_selector + " .reverse_button").on('click', (_) => {this.play(-1);});
        $(div_selector + " .play_button").on('click', (_) => {this.play(+1);});
        $(div_selector + " .stop_button").on('click', (_) => {this.stop_button_pressed();});
        $(div_selector + " .last_button").on('click', (_) => {this.goto_frame(1e10);});
        $(div_selector + " .next_frame").on('click',  (_) => {this.goto_frame(this.frame_number+1);});
        $(div_selector + " .prev_frame").on('click',  (_) => {this.goto_frame(this.frame_number-1);});
        $(div_selector + " .frame_number_field").on('input', (_) => {
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

    /*
     * loads the description of the movie and annotations
     */
    load_movie( frames ){
        // frames is a dictionary with [nn] frame number indexes.
        // frames[0] is the first element.
        // frames[0].frame_url - the URL of the first frame
        // frames[0].markers[] - an array of marker objects
        this.frames = frames;
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
        console.log("div_selector4=",this.div_selector);


        frame = parseInt(frame);         // make sure it is integer
        if ( isNaN(frame) || frame<0 ) {
            frame = 0;
        }

        if (frame>this.frames.length) {
            frame = this.frames.length-1;
        }

        if (frame==this.frame_number && !(frame===null)) {
            console.log("frame=",frame,"this.frame_number=",this.frame_number);
            return;             // did not change
        }

        console.log("frame=",frame,"this.frames[frame]=",this.frames[frame]);
        /* set the frame number, clear the screen and repaint the objects */
        this.frame_number = frame;
        this.clear_objects();
        this.set_background_image( this.frames[frame].frame_url );
        if (this.frames[frame].trackpoints) {
            for (let tp of this.frames[frame].trackpoints) {
                this.add_object( Marker(tp.x, tp.y, 10, 'red', 'red', tp.label ));
            }
        }
        this.set_movie_control_buttons();     // enable or disable buttons as appropriate
    }

    /** play is using for playing (delta=+1) and reversing (delta=-1).
     * It's called by the timer or when the button is pressed
     */
    play(delta) {
        var next_frame=0;
        if (this.timer) {
            clearTimeout(this.timer);
            this.timer = null;
        }
        if (delta>0) {
            if (this.frame_number >= this.frames.length) {
                if (this.loop) {
                    next_frame = 0;
                }
                else {
                    this.playing = false;
                }
            } else {
                next_frame = this.frame_number + delta;
            }
        }
        if (delta<0) {
            if (this.frame_number == 0) {
                if (this.loop) {
                    next_frame = this.frames.length-1;
                }
                else {
                    this.playing = false;
                    return;
                }
            } else {
                next_frame = this.frame_number + delta;
            }
        }
        this.playing=true;
        this.goto_frame(next_frame);
        this.timer = setTimeout( () => {this.timer=null;play(delta);}, PLAY_MSEC );
        this.set_movie_control_buttons();     // enable or disable buttons as appropriate
    }

    stop_button_pressed() {
        if (this.timer) {
            clearTimeout(this.timer);
            this.timer = null;
        }
        this.set_movie_control_buttons();     // enable or disable buttons as appropriate
    }


    set_movie_control_buttons() {
        console.log("div_selector3=",this.div_selector);

        // no frames, nothing is enabled
        if (this.frames.length==0){
            $(this.div_selector + ' input.frame_movement').prop('disabled',true);
            $(this.div_selector + ' input.frame_stoppage').prop('disabled',true);
            return;
        }
        // if playing, everything but 'stop' is disabled
        if (this.playing) {
            $(this.div_selector + ' input.frame_movement').prop('disabled',true);
            $(this.div_selector + ' input.frame_stoppage').prop('disabled',false);
            return;
        }
        // movie not playing
        console.log("movie not playing. forwards=",this.frame_number==this.length-1);
        $(this.div_selector + ' input.frame_stoppage').prop('disabled',true);
        $(this.div_selector + ' input.frame_movement_backwards').prop('disabled', this.frame_number==0); // can't move backwards
        var sel = this.div_selector + ' input.frame_movement_forwards';
        var val = this.frame_number==this.length-1;
        console.log("sel=",sel,"val=",val);
        $(sel).prop('disabled', val); // can't move forwards
    }
}

export { MovieController };
