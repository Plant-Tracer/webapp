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

***/

/*global api_key */
/*global movie_id */

const DEFAULT_R = 10;           // default radius of the marker
//const DEFAULT_FRAMES = 20;      // default number of frames to show
//const DEFAULT_WIDTH = 340;
//const DEFAULT_HEIGHT= 340;
const MIN_MARKER_NAME_LEN = 4;  // markers must be this long (allows 'apex')
const STATUS_WORKER = document.currentScript.src.replace("analyze.js","analyze_status_worker.js");
const TRACK_MOVIE_WORKER = document.currentScript.src.replace("analyze.js","analyze_track_movie_worker.js");

/* MyCanvasController Object - creates a canvas that can manage MyObjects */

var cell_id_counter = 0;
var div_id_counter  = 0;
var div_template = '';          // will be set with the div template
const ENGINE = 'CV2';
const ENGINE_VERSION = '1.0';

// available colors
// https://sashamaps.net/docs/resources/20-colors/
// removing green (for obvious reasons)
const CIRCLE_COLORS = ['#ffe119', '#f58271', '#f363d8', '#918eb4',
                     '#46f0f0', '#f032e6', '#bcf60c', '#fabebe', '#008080', '#e6beff',
                     '#9a6324', '#fffac8', '#800000', '#aaffc3', '#808000', '#ffd8b1',
                       '#000075', '#808080', '#e6194b', ];

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
        this.ctx.clearRect(0, 0, this.c.width, this.c.height);

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


/* MyObject --- base object for CanvasController system */
class MyObject {
    constructor(x, y, name) {
        this.x = x;
        this.y = y;
        this.name = name;
    }
    // default - it never contains the point
    contains_point(_pt) {
        return false;
    }
}

/* myCircle Object - Draws a circle radius (r) at (x,y) with fill and stroke colors
 */

class myCircle extends MyObject {
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

// The PlantTracerController is the box where we control the plant tracer functionality.
// Create the canvas and wire up the buttons for add_marker button
class PlantTracerController extends CanvasController {
    constructor( this_id, movie_id, frame_number, movie_metadata ) {
        super( `#canvas-${this_id}`, `#zoom-${this_id}` );

        //console.log("movie_metadata:",movie_metadata);

        this.this_id         = this_id;
        this.canvasId        = 0;
        this.movie_id        = movie_id;       // the movie being analyzed
        this.frame_number    = frame_number; //
        this.movie_metadata  = movie_metadata;
        this.last_tracked_frame = movie_metadata.last_tracked_frame;
        this.tracked_movie        = $(`#${this.this_id} .tracked_movie`);
        this.tracked_movie_status = $(`#${this.this_id} .tracked_movie_status`);
        this.add_marker_status    = $(`#${this_id}      .add_marker_status`);
        this.download_link        = $(`#${this.this_id} .download_link`);

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

        if (this.last_tracked_frame > 0 ){
            $(`#${this.this_id} input.track_button`).val( 'retrack movie' );
            this.download_link.show();
        }

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

        this.frame_number_field = $(`#${this.this_id} input.frame_number_field`);

        // Wire up the movement buttons
        $(`#${this.this_id} input.frame_prev10`).on('click', (_event) => {this.goto_frame( this.frame_number-10);});
        $(`#${this.this_id} input.frame_prev`)  .on('click', (_event) => {this.goto_frame( this.frame_number-1);});
        $(`#${this.this_id} input.frame_next`)  .on('click', (_event) => {this.goto_frame( this.frame_number+1);});
        $(`#${this.this_id} input.frame_next10`).on('click', (_event) => {this.goto_frame( this.frame_number+10);});

        $(`#${this.this_id} input.frame_number_field`).on('input', (_event) => {
            let new_frame = this.frame_number_field[0].value;
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
            console.log("input ",new_frame);
            this.goto_frame( new_frame );
        });
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
            this.insert_circle( 50, 50, this.marker_name_input.val());
            this.marker_name_input.val("");
        }
    }

    // add a tracking circle with the next color
    insert_circle(x, y, name) {
        // Find out how many circles there are
        let count = 0;
        for (let i=0;i<this.objects.length;i++){
            if (this.objects[i].constructor.name == myCircle.name) count+=1;
        }

        let color = CIRCLE_COLORS[count];
        this.objects.push( new myCircle(x, y, DEFAULT_R, color, color, name));
        this.create_marker_table();
        // Finally enable the track-to-end button
        this.track_button.prop('disabled',false);
    }

    create_marker_table() {
        // Generate the HTML for the table body
        let rows = '';
        for (let i=0;i<this.objects.length;i++){
            let obj = this.objects[i];
            if (obj.constructor.name == myCircle.name){
                obj.table_cell_id = "td-" + (++cell_id_counter);
                rows += `<tr>` +
                    `<td class="dot" style="color:${obj.fill};">●</td>` +
                    `<td>${obj.name}</td>` +
                    `<td id="${obj.table_cell_id}">${obj.loc()}</td><td>n/a</td><td class="del-row" object_index="${i}" >🚫</td></tr>`;
            }
        }
        $(`#${this.this_id} tbody.marker_table_body`).html( rows );
        this.redraw('insert_circle');

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
    }

    // Movement finished; upload new annotations
    object_move_finished(_obj) {
        this.put_trackpoints();
    }

    // Return an array of JSON trackpoints
    get_trackpoints() {
        let trackpoints = [];
        for (let i=0;i<this.objects.length;i++){
            let obj = this.objects[i];
            if (obj.constructor.name == myCircle.name){
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
        //console.log("put-frame-analysis: ",put_frame_analysis_params);
        $.post('/api/put-frame-analysis', put_frame_analysis_params ).done( (data) => {
            if (data.error) {
                alert("Error saving annotations: "+data.message);
            }
        });
    }

    /* track_to_end() is called when the track_button ('track to end') button is clicked.
     * It tracks on the server, then displays the new movie and offers to download a CSV file.
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
        console.log("track_to_end start");
        this.tracked_movie.hide();
        this.tracked_movie_status.text("Tracking movie...");
        this.tracked_movie_status.show();
        let movie_tracker_worker = new Worker(TRACK_MOVIE_WORKER);
        let movie_tracker_args = {
            api_key:api_key,
            movie_id:this.movie_id,
            frame_start:this.frame_number,
            engine_name: ENGINE,
            engine_version: ENGINE_VERSION
        };
        movie_tracker_worker.onmessage = (e) => {
            // Got the tracked movie back!
            if (e.data.error) {
                this.tracked_movie_status.text("Tracking error: "+data.message);
                return;
            }
            const tracked_movie_url = `/api/get-movie-data?api_key=${api_key}&movie_id=${e.data.tracked_movie_id}`;
            this.tracked_movie.html(`<source src='${tracked_movie_url}' type='video/mp4'>`); // download link for it
            this.tracked_movie_status.hide();
            this.tracked_movie.show();
            this.download_link.show();
            $(`#${this.this_id} input.track_button`).val( `retrack movie.` ); // change from 'track movie' to 'retrack movie'

            // redraw the current frame
            const get_frame_params = {
                api_key :api_key,
                movie_id:this.movie_id,
                frame_number:this.frame_number,
                format:'json',
            };
            $.post('/api/get-frame', get_frame_params).done( (data) => {this.get_frame_handler(data);});
            movie_tracker_worker.terminate();
        };
        // Track the movie - parameters for the call
        movie_tracker_worker.postMessage( movie_tracker_args );
    }

    // Change the frame
    goto_frame( frame ) {
        //console.log(`frame=${frame} last_tracked_frame=${this.last_tracked_frame} movie_metadata.total_frames=${this.movie_metadata.total_frames}`);
        if (this.last_tracked_frame === null){
            return;
        }
        // Make sure it is in range
        if ( isNaN(frame)) {
            frame = 0;
        }

        if (this.movie_metadata.total_frames != null && frame>this.movie_metadata.total_frames) {
            frame=this.movie_metadata.total_frames-1;
        }
        if (frame>this.last_tracked_frame) {
            frame=this.last_tracked_frame-1;
        }
        if (frame<0) frame=0;
        this.frame_number_field.val( frame );
        this.frame_number = frame;
        const get_frame_params = {
            api_key :api_key,
            movie_id:this.movie_id,
            frame_number:this.frame_number,
            format:'json',
        };
        $.post('/api/get-frame', get_frame_params).done( (data) => { this.get_frame_handler(data);});
        // And load the frame number
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
        this.objects = [];      // clear the array
        this.theImage = new myImage( 0, 0, data.data_url, this);
        this.objects.push(this.theImage );
        $(`#${this.this_id} td.message`).text( ' ' );
        if (data.frame_number>0){
            $(`#${this.this_id} input.track_button`).val( `retrack from frame ${data.frame_number} to end of movie` );
        }

        let count = 0;
        if (data.trackpoints) {
            for (let tp of data.trackpoints) {
                this.insert_circle( tp.x, tp.y, tp.label );
                count += 1;
            }
        }
        if (count==0) {
            if (data.frame_number==0) {
                // Add the initial trackpoints
                this.insert_circle( 20, 20, 'apex');
                this.insert_circle( 20, 50, 'ruler 0 mm');
                this.insert_circle( 20, 80, 'ruler 20 mm');
                this.add_marker_status.text("Place the three markers. You can also create additional markers.");
                this.add_marker_status.show();
            }
        }
        this.redraw('append_new_ptc');              // initial drawing
    }
}


/* myImage Object - Draws an image (x,y) specified by the url */
class myImage extends MyObject {
    constructor(x, y, url, ptc) {
        super(x, y, url);
        this.ptc = ptc;

        let theImage=this;
        this.draggable = false;
        this.ctx    = null;
        this.state  = 0;        // 0 = not loaded; 1 = loaded, first draw; 2 = loaded, subsequent draws
        this.img = new Image();

        // When the image is loaded, draw the entire stack again.
        this.img.onload = (_event) => {
            theImage.state = 1;
            if (theImage.ctx) {
                ptc.redraw('myImage constructor');
            }
        };

        this.draw = function (ctx) {
            // See if this is the first time we have drawn in the context.
            theImage.ctx = ctx;
            if (theImage.state > 0){
                if (theImage.state==1){
                    ptc.naturalWidth  = this.img.naturalWidth;
                    ptc.naturalHeight = this.img.naturalHeight;
                    theImage.state = 2;
                    ptc.set_zoom( 1.0 );
                }
                ctx.drawImage(this.img, 0, 0, this.img.naturalWidth, this.img.naturalHeight);
            }
        };

        // set the URL. It loads immediately if it is a here document.
        // That will make onload run, but theImge.ctx won't be set.
        // If the document is not a here document, then draw might be called before
        // the image is loaded. Hence we need to pay attenrtion to theImage.state.
        this.img.src = url;
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

        /* launch the webworker if we can */
        if (window.Worker) {
            const myWorker = new Worker(STATUS_WORKER);
            console.log("AAA this.tracked_movie_status=",window_ptc.tracked_movie_status);
            myWorker.onmessage = (e) => {
                window_ptc.tracked_movie_status.text( e.data.status );
            };
            myWorker.postMessage( {movie_id:movie_id, api_key:api_key} );
        } else {
            alert("Your browser does not support web workers. You cannot track movies.");
        }


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
