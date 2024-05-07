"use strict";
/* jshint esversion: 8 */
// code for /analyze

/***
 *
 Core idea from the following websites, but made object-oriented.
 * https://stackoverflow.com/questions/3768565/drawing-an-svg-file-on-a-html5-canvas
 * https://www.html5canvastutorials.com/tutorials/html5-canvas-circles/

 Core idea:
 - templates/analyze.html defines <div id='template'> that contains a frame of a movie and some controls.
 - With this frame, annotations can be created. They are stored on the server.
 - On startup, the <div> is stored in a variable and a first one is instantiated.
 - Pressing 'track to end of movie' asks the server to track from here to the end of the movie.

 Classes and methods:

 CanvasController - implements an object-based display onto a convas that supports selection.
 - clear_selection()
 - getMousePosition(e) - in canvas coordinates. Returns {x,y}
 - mousedown_handler(e) - for selection
 - mousemove_handler(e) - for dragging.
 - mouseup_handler(_) - for dragging
 - set_zoom(factor) - because we can zoom!
 - redraw( _msg) - draws all of the objects into the canvas. Currently flashes. Should use double-buffering.. calls draw of all objects
 - object_did_move( _obj) {} - for subclasses. Every move.
 - object_move_finished( _obj) {} - for sublcass

 AbstractObject - base object class
 MyCircle:AbstractObject - draws a circle. Used for track points.
 - draw
 - contains_point() - used for hit detection
 - loc() - returns location as an "x,y" string

 MyImage - draws an image specified by a URL
 - draw

 PlantTracerCanvas - Implements the functionality for the user interface, including the movie player and the track buttons.
 This is a component so we could have multiple planttracers on the screen. Probably not needed at this point.
 - marker_name_input_handler - called when something is typed in the 'new marker name' box
 - add_marker_onclick_handler - called when "add_new_marker" button is clicked
 - add_marker - adds a marker to the canvas stack
 - create_marker_table - creates the HTML for the marker table and adds to the DOM
 - del_row - deletes a row in the marker table
 - object_did_move - picks up movements in the marker and updates the table
 - object_move_finished - runs put_trackpoints, which uploads the new trackpoints to the server
 - get_trackpoints - returns an array of the trackpoints. Each trackpoint is a {x,y,label}
 - json_trackpoints - returns the trackpoints as an actual JSON list
 - put_trackpoints - sends the trackpoints to the server for the current frame using /api/put-frame-analysis
 - track_to_end - called when the 'retrack' or 'track' button is pressed. Starts the window worker and sends a track message to server.
 - movie_tracked - called when the movie tracking is finished. Terminates the status worker, gets the new trackpoints.
 - goto_frame( frame) - jumps to the requested frame number
 - set_movie_control_buttons() - enable or disable the movie control buttons

 Frames are numbered from 0 to (total_frames)-1
***/

/*global api_key */
/*global movie_id */


/* MyCanvasController Object - creates a canvas that can manage AbstractObjects */

/*
 * CanvasController maintains a set of objects that can be on the canvas and allows them to be moved and drawn.
 * Objects implemented below:
 * AbstractObject - base class
 * MyCircle - draws a circle
 * MyImage  - draws an image (from a URL). Used to draw movie animations.
 * myPath   - draws a line or, with many lines, a path
 */
class CanvasController {
    constructor(canvas_selector, zoom_selector) {      // html_id is where this canvas gets inserted
        let canvas = $( canvas_selector );
        if (canvas == null) {
            console.log("CanvasController: Cannot find canvas=", canvas_selector);
            return;
        }

        this.c   = canvas[0];     // get the element
        this.ctx = this.c.getContext('2d');                  // the drawing context

        this.selected = null,             // the selected object
        this.objects = new Array();                // the objects
        this.zoom    = 1;                 // default zoom

        // Register my events.
        // We use '=>' rather than lambda becuase '=>' wraps the current environment (including this),
        // whereas 'lambda' does not.
        // Prior, I assigned this to `me`. Without =>, 'this' points to the HTML element that generated the event.
        // This took me several hours to figure out.
        this.c.addEventListener('mousemove', (e) => {this.mousemove_handler(e);} , false);
        this.c.addEventListener('mousedown', (e) => {this.mousedown_handler(e);} , false);
        this.c.addEventListener('mouseup',   (e) => {this.mouseup_handler(e);}, false);

        // Catch the zoom change event
        console.log("startup. zoom_selector=",zoom_selector,"this=",this);
        if (zoom_selector) {
            this.zoom_selector = zoom_selector;
            $(this.zoom_selector).on('change', (_) => {
                this.set_zoom_from_selector();
            });
        }
    }

    // Selection Management
    clear_selection() {
        if (this.selected) {
            this.selected = null;
        }
    }

    getMousePosition(e) {
        let rect = this.c.getBoundingClientRect();
        return { x: (Math.round(e.x) - rect.left) / this.zoom,
                 y: (Math.round(e.y) - rect.top) / this.zoom };
    }

    mousedown_handler(e) {
        let mousePosition = this.getMousePosition(e);
        // if an object is selected, unselect it
        this.clear_selection();

        // find the object clicked in
        for (let i = 0; i < this.objects.length; i++) {
            let obj = this.objects[i];
            if (obj.draggable && obj.contains_point( mousePosition)) {
                this.selected = obj;
                // change the cursor to crosshair if something is selected
                this.c.style.cursor='crosshair';
            }
        }
        this.redraw('mousedown_handler');
    }

    mousemove_handler(e) {
        if (this.selected == null) {
            return;
        }
        const mousePosition = this.getMousePosition(e);

        // update position
        // Update the position in the selected object
        this.selected.x = mousePosition.x;
        this.selected.y = mousePosition.y;
        this.redraw('mousemove_handler');
        this.object_did_move(this.selected);
    }

    mouseup_handler(_) {
        // if an object is selected, unselect and change back the cursor
        let obj = this.selected;
        this.clear_selection();
        this.c.style.cursor='auto';
        this.redraw('mouseup_handler');
        this.object_move_finished(obj);
    }

    set_zoom(factor) {
        this.zoom = factor;
        this.c.width = this.naturalWidth * factor;
        this.c.height = this.naturalHeight * factor;
        this.redraw('set_zoom');
    }

    set_zoom_from_selector() {
        this.set_zoom( $(this.zoom_selector).val() / 100 );
    }

    // Main drawing function:
    redraw( _msg ) {
        // clear canvas
        // this is useful for tracking who called redraw, and how many times it is called, and when
        // console.log(`redraw=${msg} id=${this.c.id}`);
        // We don't need to do it if the 0th object draws to the bounds
        if ((this.objects.length > 0)
            && (this.objects[0].fills_bounds)
            && (this.objects[0].x == 0)
            && (this.objects[0].y == 0)
            && (this.objects[0].width == this.naturalWidth )
            && (this.objects[0].height == this.naturalHeight)){
        } else {
            this.ctx.clearRect(0, 0, this.c.width, this.c.height);
        }

        // draw the objects. Always draw the selected objects after
        // the unselected (so they are on top)
        this.ctx.save();
        this.ctx.scale(this.zoom, this.zoom);
        for (let s = 0; s<2; s++){
            for (let i = 0; i< this.objects.length; i++){
                let obj = this.objects[i];
                if ((s==0 && this.selected!=obj) || (s==1 && this.selected==obj)){
                    obj.draw( this.ctx , this.selected==obj);
                }
            }
        }
        this.ctx.restore();
    }

    // These can be subclassed
    object_did_move( _obj) { }
    object_move_finished( _obj) { }
}

/* CanvasItem --- base object for CanvasController system */
class CanvasItem {
    constructor(x, y, name) {
        this.x = x;
        this.y = y;
        this.name = name;
        this.fills_bounds = false; // does not fill bounds
    }

    // default - it never contains the point. Subclass this
    contains_point(_pt) {
        return false;
    }

    // Return the location as an "x,y" string
    loc() {
        return "(" + Math.round(this.x) + "," + Math.round(this.y) + ")";
    }
}

/* Marker Object - Draws a circle radius (r) at (x,y) with fill and stroke colors
 */

class Marker extends CanvasItem {
    constructor(x, y, r, fill, stroke, name) {
        super(x, y, name);
        this.startingAngle = 0;
        this.endAngle = 2 * Math.PI;
        this.r = r;
        this.draggable = true;
        this.fill = fill;
        this.stroke = stroke;
        this.name = name;
    }

    draw(ctx, selected) {
        ctx.save();
        ctx.globalAlpha = 0.5;
        if (selected) {
            // If we are selected, the cursor is cross-hair.
            // If we are not selected, we might want to draw the cross-hair
        }

        ctx.beginPath();
        ctx.arc(this.x, this.y, this.r, this.startingAngle, this.endAngle);
        ctx.fillStyle = this.fill;
        ctx.lineWidth = 3;
        ctx.fill();
        ctx.strokeStyle = this.stroke;
        ctx.stroke();
        ctx.globalAlpha = 1.0;
        ctx.font = '18px sanserif';
        ctx.fillText( this.name, this.x+this.r+5, this.y+this.r/2);
        ctx.restore();
    }

    contains_point(pt) {
        // return true if the point (x,y) is inside the circle
        let areaX = pt.x - this.x;
        let areaY = pt.y - this.y;
        //return true if x^2 + y^2 <= radius squared.
        let contained = areaX * areaX + areaY * areaY <= this.r * this.r;
        return contained;
    }

}

/* WebImage Object - Draws an image (x,y) specified by the url.
 * This is the legacy system.
 *
 * State machine:
 * state 0 = not loaded;
 * state 1 = loaded, first draw. Likely requires resizing, since we don't know the size when loaded.
 * state 2 = loaded, subsequent draws
 */
class WebImage extends CanvasItem {
    //
    constructor(x, y, url, ptc) {
        super(x, y, url);       // url is the name
        this.ptc = ptc;
        this.draggable = false;
        this.ctx    = null;
        this.state  = 0;
        this.img = new Image();

        // Overwrite the Image's onload method so that when the image is loaded, draw the entire stack again.
        this.img.onload = (_) => {
            console.log("image loaded img=",this.img.naturalWidth, this.img.naturalHeight);
            this.state = 1;
            if (this.ctx) {
                ptc.redraw('WebImage constructor');
            }
        };

        // set the URL. It loads immediately if it is a here document.
        // That will make onload run, but theImge.ctx won't be set.
        // If the document is not a here document, then draw might be called before
        // the image is loaded. Hence we need to pay attenrtion to theImage.state.
        this.img.src = url;
    }

    // WebImage draw
    draw(ctx, selected) {
        this.ctx = ctx;         // context in which we draw
        if (this.state > 0){
            // See if this is the first time we have drawn in the context. If so, resize
            if (this.state==1){
                this.width  = this.ptc.c.width = this.ptc.naturalWidth  = this.img.naturalWidth;
                this.height = this.ptc.c.height = this.ptc.naturalHeight = this.img.naturalHeight;
                this.fills_bounds = true;
                this.state = 2;
            }
            ctx.drawImage(this.img, 0, 0, this.img.naturalWidth, this.img.naturalHeight);
        }
    }
}

export { CanvasController, CanvasItem, Marker, WebImage };
