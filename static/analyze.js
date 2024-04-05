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

const PLAY_MSEC = 100;          // how fast to play
const DEFAULT_R = 10;           // default radius of the marker
const MIN_MARKER_NAME_LEN = 4;  // markers must be this long (allows 'apex')
const STATUS_WORKER = document.currentScript.src.replace("analyze.js","analyze_status_worker.js");

/* MyCanvasController Object - creates a canvas that can manage AbstractObjects */

var cell_id_counter = 0;
var div_id_counter  = 0;
var div_template = '';          // will be set with the div template
const ENGINE = 'CV2';
const ENGINE_VERSION = '1.0';
const TRACKING_COMPLETED_FLAG='TRACKING COMPLETED';

// available colors
// https://sashamaps.net/docs/resources/20-colors/
// removing green (for obvious reasons)
const CIRCLE_COLORS = ['#ffe119', '#f58271', '#f363d8', '#918eb4',
                     '#46f0f0', '#f032e6', '#bcf60c', '#fabebe', '#008080', '#e6beff',
                     '#9a6324', '#fffac8', '#800000', '#aaffc3', '#808000', '#ffd8b1',
                       '#000075', '#808080', '#e6194b', ];

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
        if (zoom_selector) {
            $(zoom_selector).on('change', (_) => {
                this.set_zoom( $(zoom_selector).val() / 100 );
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


/* AbstractObject --- base object for CanvasController system */
class AbstractObject {
    constructor(x, y, name) {
        this.x = x;
        this.y = y;
        this.name = name;
        this.fills_bounds = false; // does not fill bounds
    }
    // default - it never contains the point
    contains_point(_pt) {
        return false;
    }
}

/* MyCircle Object - Draws a circle radius (r) at (x,y) with fill and stroke colors
 */

class MyCircle extends AbstractObject {
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

    // Return the location as an "x,y" string
    loc() {
        return "(" + Math.round(this.x) + "," + Math.round(this.y) + ")";
    }
}

/* MyImage Object - Draws an image (x,y) specified by the url */
class MyImage extends AbstractObject {
    constructor(x, y, url, ptc) {
        super(x, y, url);
        this.ptc = ptc;

        this.draggable = false;
        this.ctx    = null;
        this.state  = 0;        // 0 = not loaded; 1 = loaded, first draw; 2 = loaded, subsequent draws
        this.img = new Image();

        // Overwrite the Image's onload method so that when the image is loaded, draw the entire stack again.
        this.img.onload = (_) => {
            this.state = 1;
            if (this.ctx) {
                ptc.redraw('MyImage constructor');
            }
        };

        // set the URL. It loads immediately if it is a here document.
        // That will make onload run, but theImge.ctx won't be set.
        // If the document is not a here document, then draw might be called before
        // the image is loaded. Hence we need to pay attenrtion to theImage.state.
        this.img.src = url;
    }

    draw(ctx, selected) {
        // See if this is the first time we have drawn in the context.
        this.ctx = ctx;
        if (this.state > 0){
            if (this.state==1){
                this.width  = this.ptc.naturalWidth  = this.img.naturalWidth;
                this.height = this.ptc.naturalHeight = this.img.naturalHeight;
                this.fills_bounds = true;
                this.state = 2;
                this.ptc.set_zoom( 1.0 ); // default zoom
            }
            ctx.drawImage(this.img, 0, 0, this.img.naturalWidth, this.img.naturalHeight);
        }
    }
}

// The PlantTracerController is the box where we control the plant tracer functionality.
// Create the canvas and wire up the buttons for add_marker button
class PlantTracerController extends CanvasController {
    constructor( this_id, movie_id, frame_number, movie_metadata ) {
        super( `#canvas-${this_id}`, `#zoom-${this_id}` );
        this.this_id         = this_id;
        this.canvasId        = 0;
        this.movie_id        = movie_id;       // the movie being analyzed
        this.frame_number    = frame_number;   // current frame number
        this.movie_metadata  = movie_metadata;
        this.total_frames    = movie_metadata.total_frames;
        this.last_tracked_frame = movie_metadata.last_tracked_frame;
        this.tracked_movie        = $(`#${this.this_id} .tracked_movie`);
        this.tracked_movie_status = $(`#${this.this_id} .tracked_movie_status`);
        this.add_marker_status    = $(`#${this_id}      .add_marker_status`);
        this.download_link        = $(`#${this.this_id} .download_link`);
        this.download_button      = $(`#${this.this_id} .download_button`);
        this.playing = 0;
        console.log("PlantTracer movie_id=",movie_id,"metadata=",movie_metadata);

        this.download_link.attr('href',`/api/get-movie-trackpoints?api_key=${api_key}&movie_id=${movie_id}`);

        // Size the canvas and video player if we know the sizes
        if (this.movie_metadata.width && this.movie_metadata.height) {
            $(`#${this.this_id} canvas`).attr('width',this.movie_metadata.width);
            $(`#${this.this_id} canvas`).attr('height',this.movie_metadata.height);
            $(`#${this.this_id} video`).attr('width',this.movie_metadata.width);
            $(`#${this.this_id} video`).attr('height',this.movie_metadata.height);
        }

        // Hide the download link until we track or retrack
        this.download_link.hide();

        // Hide the video until we track or retrack retrack
        this.tracked_movie.hide();
        this.tracked_movie_status.hide();

        // marker_name_input is the text field for the marker name
        this.marker_name_input = $(`#${this_id} input.marker_name_input`);
        this.marker_name_input.on('input',   (event) => { this.marker_name_input_handler(event);});
        this.marker_name_input.on('keydown', (event) => { if (event.keyCode==13) this.add_marker_onclick_handler(event);});

        // We need to be able to enable or display the add_marker button, so we record it
        this.add_marker_button = $(`#${this_id} input.add_marker_button`);
        this.add_marker_button.on('click', (event) => { this.add_marker_onclick_handler(event);});

        // We need to be able to enable or display the
        this.track_button = $(`#${this_id} input.track_button`);
        this.track_button.on('click', (event) => {this.track_to_end(event);});
        this.track_button.prop('disabled',true); // disable it until we have a marker added.

        this.download_button = $(`#${this_id} input.download_button`);

        $(`#${this.this_id} span.total-frames-span`).text(this.total_frames);

        this.frame_number_field = $(`#${this.this_id} input.frame_number_field`);
        this.frame0_button = $(`#${this.this_id} input.frame0_button`);
        this.frame0_button.prop('disabled',false);
        this.frame0_button.on('click', (_event) => {this.goto_frame(0);});
        this.play_button = $(`#${this.this_id} input.play_button`);
        this.play_button.prop('disabled',false);
        this.play_button.on('click', (_event) => {this.play_button_pressed();});

        this.stop_button = $(`#${this.this_id} input.stop_button`);
        this.stop_button.prop('disabled',true);
        this.stop_button.on('click', (_event) => {this.stop_button_pressed();});

        this.track_button = $(`#${this.this_id} input.track_button`);

        // Wire up the movement buttons
        $(`#${this.this_id} input.frame_prev10`).on('click', (_event) => {this.goto_frame( parseInt(this.frame_number)-10);});
        $(`#${this.this_id} input.frame_prev`)  .on('click', (_event) => {this.goto_frame( parseInt(this.frame_number)-1);});
        $(`#${this.this_id} input.frame_next`)  .on('click', (_event) => {this.goto_frame( parseInt(this.frame_number)+1);});
        $(`#${this.this_id} input.frame_next10`).on('click', (_event) => {this.goto_frame( parseInt(this.frame_number)+10);});

        $(`#${this.this_id} input.frame_number_field`).on('input', (_event) => {
            let new_frame = this.frame_number_field[0].value;
            console.log("frame_number_field number changed to ",new_frame);
            // turn '' into a "0"
            if (new_frame=='') {
                new_frame='0';
                this.frame_number_field[0].value=new_frame;
            }
            // remove leading 0
            if (new_frame.length == 2 && new_frame[0]=='0') {
                new_frame = new_frame[1];
                this.frame_number_field[0].value=new_frame;
            }
            this.goto_frame( new_frame );
        });

        if (this.last_tracked_frame > 0 ){
            this.track_button.val( 'retrack movie' );
            this.download_link.show();
        }
    }


    // on each change of input, validate the marker name
    marker_name_input_handler (_e) {
        const val = this.marker_name_input.val();
        // First see if marker name is too short
        if (val.length < MIN_MARKER_NAME_LEN) {
            this.add_marker_status.text("Marker name must be at least "+MIN_MARKER_NAME_LEN+" letters long");
            this.add_marker_button.prop('disabled',true);
            return;
        } else {
            this.add_marker_status.text("");
            this.add_marker_button.prop('enabled',true);
        }
        // Make sure it isn't in use
        for (let i=0;i<this.objects.length; i++){
            if(this.objects[i].name == val){
                this.add_marker_status.text("That name is in use, choose another.");
                this.add_marker_button.prop('disabled',true);
                return;
            }
        }
        this.add_marker_status.text('');
        this.add_marker_button.prop('disabled',false);
    }

    // new marker added
    add_marker_onclick_handler(_e) {
        if (this.marker_name_input.val().length >= MIN_MARKER_NAME_LEN) {
            this.add_marker( 50, 50, this.marker_name_input.val());
            this.marker_name_input.val("");
        }
    }

    // add a tracking circle with the next color
    add_marker(x, y, name) {
        // Find out how many circles there are
        let count = 0;
        for (let i=0;i<this.objects.length;i++){
            if (this.objects[i].constructor.name == MyCircle.name) count+=1;
        }

        let color = CIRCLE_COLORS[count];
        this.objects.push( new MyCircle(x, y, DEFAULT_R, color, color, name));
        this.create_marker_table();
        // Finally enable the track-to-end button
        this.track_button.prop('disabled',false);
    }

    create_marker_table() {
        // Generate the HTML for the table body
        let rows = '';
        for (let i=0;i<this.objects.length;i++){
            let obj = this.objects[i];
            if (obj.constructor.name == MyCircle.name){
                obj.table_cell_id = "td-" + (++cell_id_counter);
                rows += `<tr>` +
                    `<td class="dot" style="color:${obj.fill};">●</td>` +
                    `<td>${obj.name}</td>` +
                    `<td id="${obj.table_cell_id}">${obj.loc()}</td><td>n/a</td><td class="del-row" object_index="${i}" >🚫</td></tr>`;
            }
        }
        $(`#${this.this_id} tbody.marker_table_body`).html( rows );
        this.redraw('add_marker');

        // wire up the delete object method
        $(`#${this.this_id} .del-row`).on('click', (event) => {this.del_row(event.target.getAttribute('object_index'));});
        $(`#${this.this_id} .del-row`).css('cursor','default');
    }

    // Delete a row and update the server
    del_row(i) {
        this.objects.splice(i,1);
        this.create_marker_table();
        this.put_trackpoints();
    }

    // Subclassed methods
    // Update the matrix location of the object the moved
    object_did_move(obj) {
        $( "#"+obj.table_cell_id ).text( obj.loc() );
        if (this.frame_number==0 || this.frame_number < this.movie_metadata.total_frames) {
            this.track_button.prop('disabled',false); // enable the button if track point is moved
        }
    }

    // Movement finished; upload new annotations
    object_move_finished(_obj) {
        this.put_trackpoints();
    }

    // Return an array of trackpoints
    get_trackpoints() {
        let trackpoints = [];
        for (let i=0;i<this.objects.length;i++){
            let obj = this.objects[i];
            if (obj.constructor.name == MyCircle.name){
                trackpoints.push( {x:obj.x, y:obj.y, label:obj.name} );
            }
        }
        return trackpoints;
    }

    json_trackpoints() {
        return JSON.stringify(this.get_trackpoints());
    }

    put_trackpoints() {
        // If we are putting the frame, we already have the frame_id
        let put_frame_analysis_params = {
            api_key      : api_key,
            movie_id     : this.movie_id,
            frame_number : this.frame_number,
            trackpoints  : this.json_trackpoints()
        };
        $.post('/api/put-frame-analysis', put_frame_analysis_params ).done( (data) => {
            if (data.error) {
                alert("Error saving annotations: "+data.message);
            }
        });
    }

    /* track_to_end() is called when the track_button ('track to end') button is clicked.
     * It calls the /api/track-movie-quque on the server, queuing movie tracking (which takes a while).
     * Here are some pages for notes about playing the video:
     * https://www.w3schools.com/html/tryit.asp?filename=tryhtml5_video_js_prop
     * https://developer.mozilla.org/en-US/docs/Web/HTML/Element/video
     * https://developer.mozilla.org/en-US/docs/Web/Media/Audio_and_video_delivery/Video_player_styling_basics
     * https://blog.logrocket.com/creating-customizing-html5-video-player-css/
     * https://freshman.tech/custom-html5-video/
     * https://medium.com/@nathan5x/event-lifecycle-of-html-video-element-part-1-f63373c981d3
     */
    track_to_end(_event) {
        // get the next frame and apply tracking logic
        // First launch the status worker
        /* Disabled because Amazon's back end isn't multi-threaded */
        if (window.Worker) {
            this.status_worker = new Worker(STATUS_WORKER);
            this.status_worker.onmessage = (e) => {
                // Got back a message
                console.log("got e.data=",e.data,"status=",e.data.status);
                this.tracked_movie_status.text( e.data.status );
                if (e.data.status==TRACKING_COMPLETED_FLAG) {
                    this.movie_tracked();
                    this.total_frames = e.data.total_frames;
                    $(`#${this.this_id} span.total-frames-span`).text(this.total_frames);
                }
            };
            this.status_worker.postMessage( {movie_id:movie_id, api_key:api_key} );
        } else {
            alert("Your browser does not support web workers. You cannot track movies.");
        }
        console.log("track_to_end start");
        this.tracked_movie.hide();
        this.tracked_movie_status.text("Asking server to track movie...");
        this.tracked_movie_status.show();
        this.track_button.prop('disabled',true); // disable it until tracking is finished
        const formData = new FormData();
        formData.append('api_key',api_key);
        formData.append('movie_id',this.movie_id);
        formData.append('frame_start',this.frame_number);
        formData.append('engine_name',ENGINE);
        formData.append('engine_version',ENGINE_VERSION);
        fetch('/api/track-movie-queue', {
            method:'POST',
            body: formData
        })
        .then((response) => response.json())
            .then((data) => {
                if(data.error){
                    alert(data.message);
                } else {
                    this.tracked_movie_status.text(data.message);
                }
            });
    }

    /** movie is tracked - display the results */
    movie_tracked() {
        const movie_id = this.movie_id;
        console.log(`terminating status worker; getting metadata for movie_id=${movie_id}`);
        this.status_worker.terminate();
        fetch(`/api/get-movie-metadata?api_key=${api_key}&movie_id=${movie_id}`, { method:'GET'})
            .then((response) => response.json())
            .then((data) => {
                console.log("movie metadata: ",data);
                const tracked_movie_url = `/api/get-movie-data?api_key=${api_key}&movie_id=${data.metadata.tracked_movie_id}`;
                this.tracked_movie.html(`<source src='${tracked_movie_url}' type='video/mp4'>`); // download link for it
                this.tracked_movie_status.text('Movie tracking complete.');
                this.tracked_movie.show();
                this.download_link.show();
                // change from 'track movie' to 'retrack movie' and re-enable it
                this.track_button.val( `retrack movie.` );
                this.track_button.prop('disabled',false);

                // redraw the current frame
                const get_frame_params = {
                    api_key :api_key,
                    movie_id:this.movie_id,
                    frame_number:this.frame_number,
                    format:'json',
                };
                $.post('/api/get-frame', get_frame_params).done( (data) => {this.get_frame_handler(data);});
            });
    }

    /**
     * Change the frame. This is called repeatedly when the movie is playing, with the frame number changing
     * First we verify the next frame number, then we call the /api/get-frame call to get the frame,
     * with get_frame_handler getting the data.
     *
     * Todo: cache the frames in an array.
     * Use double-buffering by drawing into an offscreen canvas and then bitblt in the image, to avoid flashing.
     */
    goto_frame( frame ) {
        console.log(`goto_frame(${frame}) total_frames=${this.total_frames} last_tracked_frame=${this.last_tracked_frame}`);
        if (this.last_tracked_frame === null){
            return;
        }
        if ( isNaN(frame) || frame<0) {
            frame = 0;
        }

        if (this.total_frames != null && frame>=this.total_frames) {
            frame=this.total_frames-1;
        }

        this.frame_number = frame;
        if (this.frame_number_field[0].value != frame ){
            this.frame_number_field[0].value = frame;
        }
        this.set_movie_control_buttons();     // enable or disable all buttons as appropriate
        // And get the frame
        const get_frame_params = {
            api_key :api_key,
            movie_id:this.movie_id,
            frame_number:this.frame_number,
            format:'json',
        };
        $.post('/api/get-frame', get_frame_params).done( (data) => { this.get_frame_handler(data);});
    }

    set_movie_control_buttons() {
        if (this.playing) {
            this.play_button.prop('disabled',true);
            this.stop_button.prop('disabled',false);
            this.track_button.prop('disabled',true);
            this.download_button.prop('disabled',true);
            $(`#${this.this_id} input.frame_movement`).prop('disabled',true); // all arrow buttons disabled
            return;
        }
        // movie not playing
        this.stop_button.prop('disabled',true);
        this.track_button.prop('disabled', this.frame_number>=this.last_tracked_frame);
        this.download_button.prop('disabled',false);
        $(`#${this.this_id} input.frame_movement_backwards`).prop('disabled', this.frame_number<=0);
        $(`#${this.this_id} input.frame_movement_forwards`).prop('disabled', this.frame_number>=this.last_tracked_frame-1);

        // We can play if we are not on the last frame
        this.play_button.prop('disabled', this.frame_number >= this.last_tracked_frame);
    }

    /***
     * play_button_pressed() is called when the play button is pressed, and each time the play timer clicks.
     * It goes to the next frame and sets another timer if we haven't reach the end.
     * The STOP button stops the timmer.
     */
    play_button_pressed() {
        if (this.frame_number < this.last_tracked_frame-1) {
            this.goto_frame( this.frame_number + 1);
            this.playTimer = setTimeout( () => this.play_button_pressed(), PLAY_MSEC);
            this.playing = 1;
        } else {
            this.stop_button_pressed(); // simulate stop button pressed at end of movie
            this.playing = 0;
        }
        this.set_movie_control_buttons();
    }

    stop_button_pressed() {
        if (this.playTimer) {
            clearTimeout(this.playTimer);
            this.playTimer = undefined;
        }
        this.playing = 0;
        this.set_movie_control_buttons();
    }

    /***
     * get_frame_handler() is called as a callback from the /api/get-frame call.
     * It sets the frame visible in the top of the component and sets up the rest of the GUI to match.
     */
    get_frame_handler( data ) {
        //console.log('RECV get_frame_handler:',data);
        if (data.error) {
            alert(`error: ${data.message}`);
            return;
        }
        // process the /api/get-frame response
        this.last_tracked_frame = data.last_tracked_frame;
        if (this.last_tracked_frame === null){
            $(`#${this.this_id} input.frame_movement`).prop('disabled',true);
        } else {
            $(`#${this.this_id} input.frame_movement`).prop('disabled',false);
            this.frame_number_field.attr('max', data.last_tracked_frame);
        }
        this.frame_number_field.val( data.frame_number );

        //console.log("this.frame_number_field=",this.frame_number_field,"val=",this.frame_number_field.val());
        // Add the markers to the image and draw them in the table
        this.theImage = new MyImage( 0, 0, data.data_url, this);
        this.objects = [];      // clear the array
        this.objects.push(this.theImage );
        $(`#${this.this_id} td.message`).text( ' ' );
        if (data.frame_number>=0){
            this.track_button.val( `retrack from frame ${data.frame_number} to end of movie` );
        }

        // Draw trakcpoints if we have them, otherwise create initial trackpoints
        let count = 0;
        if (data.trackpoints) {
            for (let tp of data.trackpoints) {
                this.add_marker( tp.x, tp.y, tp.label );
                count += 1;
            }
        }
        if (count==0) {
            if (data.frame_number==0) {
                // Add the initial trackpoints
                this.add_marker( 20, 20, 'apex');
                this.add_marker( 20, 50, 'ruler 0 mm');
                this.add_marker( 20, 80, 'ruler 20 mm');
                this.add_marker_status.text("Drag each marker to the appropriate place on the image. You can also create additional markers.");
                this.track_button.val( "Initial movie tracking." );
                this.add_marker_status.show();
            }
        }
        this.set_movie_control_buttons();
    }
}


/* update_div:
 * Callback when data arrives from /api/get-frame.
 */

/* append_new_ptc
 * - creates the <div> that includes the canvas and is controlled by the PlantTracerController.
 * - Makes a call to get-frame to get the frame
 *   - callback gets the frame and trackpoints; it draws them and sets up the event loops to draw more.
 */
// the id for the frame that is created.
// each frame is for a specific movie
function append_new_ptc(movie_id, frame_number) {
    let this_id  = "template-" + (div_id_counter++);
    //let this_sel = `${this_id}`;
    //console.log(`append_new_ptc: frame_number=${frame_number} this_id=${this_id} this_sel=${this_sel}`);

    /* Create the <div> and a new #template. Replace the current #template with the new one. */
    let div_html = div_template
        .replace('template', `${this_id}`)
        .replace('canvas-id',`canvas-${this_id}`)
        .replace('zoom-id',`zoom-${this_id}`) + "<div id='template'></div>";
    $( '#template' ).replaceWith( div_html );
    $( '#template' )[0].scrollIntoView(); // scrolls so that the next template slot (which is empty) is in view

    // Get the movie metadata.
    // When we have it, create the plant tracer controller
    $.post('/api/get-movie-metadata', {api_key:api_key, movie_id:movie_id}).done( (data) => {
        // Create the new PlantTracerController
        //console.log("data:",data);
        if (data.error==true) {
            alert(data.message);
            return;
        }
        let window_ptc = new PlantTracerController( this_id, movie_id, frame_number, data.metadata );

        // get the request frame of the movie. When it comes back, use it to populate
        // a new PlantTracerController.
        const get_frame_params = {
            api_key :api_key,
            movie_id:movie_id,
            frame_number:frame_number,
            format:'json',
        };
        //console.log("SEND get_frame_params:",get_frame_params);
        $.post('/api/get-frame', get_frame_params).done( (data) => {
            window_ptc.get_frame_handler( data );
        });
    });
}

// Called when the page is loaded
function analyze_movie() {
    console.log("analyze_movie");
    // Say which movie we are working on
    $('#firsth2').html(`Movie #${movie_id}`);

    // capture the HTML of the <div id='#template'> into a new div
    div_template = "<div id='template'>" + $('#template').html() + "</div>";

    // erase the template div's contents, leaving an empty template at the end
    $('#template').html('');

    return append_new_ptc(movie_id, 0);           // create the first <div> and its controller
    // Prime by loading the first frame of the movie.
    // Initial drawing
}

// Call analyze_move on load
$( document ).ready( function() {
    analyze_movie();
});
