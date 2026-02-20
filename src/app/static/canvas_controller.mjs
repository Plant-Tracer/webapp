"use strict";
/* jshint esversion: 8 */
/* eslint-env es6 */
/* eslint parserOptions: { "sourceType": "module" } */
import { $ } from "./utils.js";

// code for /analyze

/***
 * Canvas Controller:
 * Implements an HTML5 <canvas> that can have arbitrary objects. The individual objects support:
 *  - Selection
 *  - Dragging
 *  - Arbitrary images
 *  - Z layering
 *  - double-buffering.
 *  - zoom
 *
 Core idea from the following websites, but made object-oriented.
 * https://stackoverflow.com/questions/3768565/drawing-an-svg-file-on-a-html5-canvas
 * https://www.html5canvastutorials.com/tutorials/html5-canvas-circles/

 Core idea:

 Classes and methods:

 CanvasController - implements an object-based display onto a convas that supports selection.
 - clear_selection()
 - getMousePosition(e) - in canvas coordinates. Returns obj.x, obj.y in canvas coordinates
 - mousedown_handler(e) - for selection
 - mousemove_handler(e) - for dragging.
 - mouseup_handler(_) - for dragging
 - set_zoom(factor) - because we can zoom!
 - copyOffscreen()  - copies from the offscreen canvas to the onscreen canvas
 - redraw()    - draws in the offscreen canvas and then schedules a copyOffscreen
 - resize(w,h) - resizes the canvas and its offscreen canvas.
 - add_object() - adds an object to the display list
 - set_background_image - fetches a background image and resizes the canvas to be the size of the image.
 -
 - delegate    - if set, gets notices
 - delegate.object_did_move( _obj) {} - tells delegate that an object moved.
 - delegate.object_move_finished( _obj) {} - tells delegate that object move finished.

 CanvasItem - base object class
 MyCircle:CanvasItem - draws a circle. Used for track points.
 - draw
 - contains_point() - used for hit detection
 - loc() - returns location as an "x,y" string

 WebImage - draws an image specified by a URL
 - draw

***/

/* MyCanvasController Object - creates a canvas that can manage CanvasItems.
 * Implements double-buffering to avoid flashing in redraws.
 */

/*
 * CanvasController maintains a set of objects that can be on the canvas and allows them to be moved and drawn.
 * Objects implemented below:
 * CanvasItem - base class
 * MyCircle - draws a circle
 * WebImage  - draws an image (from a URL). Used to draw movie animations.
 * myPath   - draws a line or, with many lines, a path
 */
class CanvasController {
    constructor(canvas_selector, zoom_selector) {      // html_id is where this canvas gets inserted
        let canvas = $(canvas_selector);
        if (canvas.length == 0) {
            console.log("CanvasController: Cannot find canvas=", canvas_selector);
            return;
        }

        this.did_onload_callback = ((_) => { });   // by default, call nothing
        this.c = canvas.get(0);                // get the element
        this.ctx = this.c.getContext('2d');  // the drawing context

        this.oc = document.createElement('canvas'); // offscreen canvas
        this.oc.width = this.naturalWidth = this.c.width;
        this.oc.height = this.naturalHeight = this.c.height;
        this.octx = this.oc.getContext('2d');

        this.delegate = null;              // the delegate
        this.selected = null;              // the selected object
        this.objects = new Array();       // the objects
        this.zoom = 1;                 // default zoom

        // Register object movement events.
        // We use '=>' rather than lambda because '=>' wraps the current environment (including this),
        // whereas 'lambda' does not.
        // Without =>, 'this' points to the HTML element that generated the event.
        // This took me several hours to figure out.

        if (window.PointerEvent) {
            this.c.addEventListener('pointermove', (e) => { this.pointermove_handler(e); });
            this.c.addEventListener('pointerdown', (e) => { this.pointerdown_handler(e); });
            this.c.addEventListener('pointerup', (e) => { this.pointerup_handler(e); });
        } else {
            this.c.addEventListener('mousemove', (e) => { this.mousemove_handler(e); }, false);
            this.c.addEventListener('mousedown', (e) => { this.mousedown_handler(e); }, false);
            this.c.addEventListener('mouseup', (e) => { this.mouseup_handler(e); }, false);

            this.c.addEventListener('touchmove', (e) => { this.touchmove_handler(e); }, { passive: false });
            this.c.addEventListener('touchstart', (e) => { this.touchstart_handler(e); }, { passive: false });
            this.c.addEventListener('touchend', () => { this.touchend_handler(); }, { passive: false });
        }

        // Catch the zoom change event
        if (zoom_selector) {
            this.zoom_selector = zoom_selector;
            $(this.zoom_selector).on('change', (_) => {
                const new_zoom = $(this.zoom_selector).val() / 100.0;
                this.set_zoom(new_zoom);
            });
        }
    }

    // add an object
    add_object(obj) {
        obj.cc = this;          // We are now this object's canvas controller
        this.objects.push(obj);
    }

    // Erase each object's cc and then delete the references.
    // For the canvas_movie_controller, we end up retaining a reference for all of the images
    clear_objects() {
        for (let i = 0; i < this.objects.length; i++) {
            this.objects[i].cc = null;
        }
        this.objects.length = 0;
    }

    // Selection Management
    clear_selection() {
        if (this.selected) {
            this.selected = null;
        }
    }

    // -- pointer device-independent marker drag handling

    getPointerLocation(e) {
        let rect = this.c.getBoundingClientRect();
        return {
            x: (Math.round(e.x) - rect.left) / this.zoom,
            y: (Math.round(e.y) - rect.top) / this.zoom
        };
    }

    startMarkerDrag(e) {
        // if an object is selected, unselect it
        this.clear_selection();

        if (!e || !e.x || !e.y) {
            throw new Error('startMarkerDrag: missing or invalid event');
        }

        // find the object clicked in
        let pointerPosition = this.getPointerLocation(e);
        for (let i = 0; i < this.objects.length; i++) {
            let obj = this.objects[i];
            if (obj.draggable && obj.contains_point(pointerPosition)) {
                this.selected = obj;
                // change the cursor to crosshair if something is selected
                this.c.style.cursor = 'crosshair';
            }
        }
        this.redraw();
    }

    moveMarker(e) {
        if (this.selected == null) {
            return;
        }

        if (!e || !e.x || !e.y) {
            throw new Error('moveMarker: missing or invalid event');
        }

        const pointerPosition = this.getPointerLocation(e);

        // update position
        // Update the position in the selected object
        this.selected.x = pointerPosition.x;
        this.selected.y = pointerPosition.y;
        this.redraw();
        this.object_did_move(this.selected);
    }

    endMarkerDrag(_) {
        // if an object is selected, unselect and change back the cursor
        let obj = this.selected;
        this.clear_selection();
        this.c.style.cursor = 'auto';
        this.redraw();
        this.object_move_finished(obj);
    }

    // -- Mouse event handlers --

    mousedown_handler(e) {
        this.startMarkerDrag(e);
    }

    mousemove_handler(e) {
        this.moveMarker(e);
    }

    mouseup_handler(_) {
        this.endMarkerDrag();
    }

    // -- Touch event handlers --
    touchstart_handler(e) {
        if (e.touches.length === 1) {
            e.preventDefault();
            const touch = e.touches[0];
            let new_e = { "x": touch.clientX, "y": touch.clientY };
            this.startMarkerDrag(new_e);
        }
    }

    touchmove_handler(e) {
        if (e.touches.length === 1) {
            e.preventDefault();
            const touch = e.touches[0];
            let new_e = { "x": touch.clientX, "y": touch.clientY };
            this.moveMarker(new_e);
        }
    }

    touchend_handler() {
        this.endMarkerDrag();
    }

    // -- Pointer event handlers --
    pointerdown_handler(e) {
        e.preventDefault();
        let new_e = { "x": e.clientX, "y": e.clientY };
        this.startMarkerDrag(new_e);
        this.c.setPointerCapture(e.pointerId);
    }

    pointermove_handler(e) {
        e.preventDefault();
        let new_e = { "x": e.clientX, "y": e.clientY };
        this.moveMarker(new_e);
    }

    pointerup_handler(e) {
        this.endMarkerDrag();
        this.c.releasePointerCapture(e.pointerId);
    }

    resize(width, height) {
        this.c.width = this.naturalWidth = width;
        this.c.height = this.naturalHeight = height;
        this.redraw();
    }

    // Zoom happens by scaling the drawing with a transformation and resizing the canvas element.
    // We also have to resize the offscreen canvas

    set_zoom(factor) {
        this.zoom = factor;
        this.oc.width = this.c.width = this.naturalWidth * factor;
        this.oc.height = this.c.height = this.naturalHeight * factor;
        this.redraw();
    }

    // Main drawing function:
    redraw() {
        // redraw the object stack.
        // We don't need to clear the canvas if the first object is draws to the bounds (like it's an image).
        if (this.objects.length == 0
            || !this.objects[0].fills_bounds
            || this.objects[0].x != 0
            || this.objects[0].y != 0
            || this.objects[0].width != this.naturalWidth
            || this.objects[0].height == this.naturalHeight) {
            this.octx.clearRect(0, 0, this.oc.width, this.oc.height);
        }

        // draw the objects. Always draw the selected objects after
        // the unselected (so they are on top)
        this.octx.save();
        this.octx.scale(this.zoom, this.zoom);
        for (let s = 0; s < 2; s++) {
            for (let i = 0; i < this.objects.length; i++) {
                let obj = this.objects[i];
                if ((s == 0 && this.selected != obj) || (s == 1 && this.selected == obj)) {
                    obj.draw(this.octx, this.selected == obj);
                }
            }
        }
        this.octx.restore();
        // Now use double-buffering to copy the off-screen context to the screen.
        // We use requestAnimationFrame() to prevent flickering.
        requestAnimationFrame((_) => {
            this.ctx.clearRect(0, 0, this.c.width, this.c.height);
            this.ctx.drawImage(this.oc, 0, 0);
        });
    }

    set_background_image(url) {
        this.add_object(new WebImage(0, 0, url));
    }

    // These can be subclassed, or you can use the delegate
    object_did_move(_obj) { if (this.delegate) this.delegate.object_did_move(_obj); }
    object_move_finished(_obj) { if (this.delegate) this.delegate.object_move_finished(_obj); }
}


/* CanvasItem --- base object for CanvasController system */
class CanvasItem {
    constructor(x, y, name) {
        this.x = x;             // every item has an x, but I'm not sure why
        this.y = y;             // every item has a y
        this.name = name;
        this.fills_bounds = false; // does not fill bounds, does this make sense? We don't have bounds
        this.cc = null;            // currently no controller
    }

    // default - it never contains the point. Subclass this
    contains_point(_pt) {
        return false;
    }

    // default - subclasses should override this
    draw(ctx, selected) {
        ctx.save();
        ctx.fillText(this.name, this.x, this.y);
        ctx.restore();
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
        this.r = r;        // in pixels
        this.draggable = true;  // boolean
        this.fill = fill;     // string for color
        this.stroke = stroke;   // string for color
        this.name = name;     //
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
        ctx.fillText(this.name, this.x + this.r + 5, this.y + this.r / 2);
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

class Line extends CanvasItem {
    constructor(x, y, x2, y2, width, color) {
        super(x, y, 'line');
        this.x2 = x2;
        this.y2 = y2;
        this.width = width;
        this.color = color;
    }

    draw(ctx, selected) {
        ctx.save();
        ctx.beginPath();
        ctx.lineWidth = this.width;
        ctx.moveTo(this.x, this.y);
        ctx.lineTo(this.x2, this.y2);
        ctx.strokeStyle = this.color;
        ctx.stroke();
        ctx.restore();
    }
}


class Text extends CanvasItem {
    constructor(x, y, text, color = 'black') {
        super(x, y, text);
        this.font = '18px sanserif';
        this.color = color;
    }

    draw(ctx, selected) {
        ctx.save();
        ctx.font = this.font;
        ctx.fillText(this.name, this.x, this.y);
    }
}


/* WebImage Object - Draws an image (x,y) specified by the url.
 * This is the legacy system.
 *
 */
const maxRetries = 10;
const retryInterval = 2000;

class WebImage extends CanvasItem {
    constructor(x, y, url) {
        super(x, y, url);       // url is the name
        this.draggable = false;
        this.url = url;
        this.img = new Image();
        this.loaded = false;
        this.fills_bounds = true;
        this.width = 0;
        this.height = 0;
        this.retries = 0;
        this.timeout = null;

        // Overwrite the Image's onload method so that when the image is loaded, draw the entire stack again.
        this.img.onload = (_) => {
            //console.log(`image loaded ${this.url} ${this.img.naturalWidth}x${this.img.naturalHeight}`);
            if (this.timeout) {
                clearTimeout(this.timeout);
                this.timeout = null;
            }
            this.width = this.img.naturalWidth;
            this.height = this.img.naturalHeight;
            this.loaded = true;
            // If we are already in a canvas controller, as it to redraw.
            // If we are not yet in a canvas controller, redraw
            if (this.cc) {
                this.cc.redraw();
                this.cc.did_onload_callback(this);
            }
        };

        this.img.onerror = (_) => {
            console.log("image onerror ", this.url);
            // Clear the timeout if it is still set
            if (this.timeout) {
                clearTimeout(this.timeout);
                this.timeout = null;
            }
            if (this.loaded) {
                console.log(this.url, "loaded; won't retry.");
                return;
            }

            console.log("this.retries=", this.retries, "maxRetries=", maxRetries);
            if (this.retries < maxRetries) {
                this.retries++;
                console.log(`image failed ${this.url} retrying ${this.retries}`)
                this.img.src = ''; // clear the source to ensure that browser attempts a reload
                this.img.src = this.url; // queue reload
                this.timeout = setTimeout(
                    () => { this.img.onerror(); }, retryInterval); // que another retry
            }
        };

        // set the URL. It loads immediately if it is a here document.
        // That will make onload run, but theImge.ctx won't be set.
        // If the document is not a here document, then draw might be called before
        // the image is loaded. Hence we need to pay attenrtion to theImage.state.
        this.img.src = url;
        this.timeout = setTimeout(
            () => { this.img.onerror(); }, retryInterval); // quey a retry
    }

    // WebImage draw
    draw(ctx, selected) {
        if (this.loaded) {
            ctx.drawImage(this.img, this.x, this.y, this.img.naturalWidth, this.img.naturalHeight);
        } else {
            ctx.fillText(this.img.src, this.x, this.y, this.img.naturalWidth + selected);
        }
    }
}

export { CanvasController, CanvasItem, Marker, WebImage, Line, Text };
