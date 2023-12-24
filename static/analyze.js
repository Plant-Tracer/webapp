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

const DEFAULT_R = 10;           // default radius of the marker
const DEFAULT_FRAMES = 20;      // default number of frames to show
const DEFAULT_WIDTH = 340;
const DEFAULT_HEIGHT= 340;
const MIN_MARKER_NAME_LEN = 5;  // markers must be this long

/* MyCanvasController Object - creates a canvas that can manage MyObjects */

var cell_id_counter = 0;
var div_id_counter  = 0;
var template_html   = null;
const ENGINE = 'CV2';

class CanvasController {
    constructor(canvas_selector, zoom_selector) {      // html_id is where this canvas gets inserted
        let canvas = $( canvas_selector );
        if (canvas == null) {
            console.log("CanvasController: Cannot find canvas ",canvas_controller);
            return;
        } else {
            console.log("CanvasController: canvas_selector=",canvas_selector);
        }

        this.c   = canvas[0];     // get the element
        this.ctx = this.c.getContext('2d');                  // the drawing context

        this.selected = null,             // the selected object
        this.objects = [];                // the objects
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
            $(zoom_selector).on('change', (e) => {
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
        var rect = this.c.getBoundingClientRect();
        return { x: (Math.round(e.x) - rect.left) / this.zoom,
                 y: (Math.round(e.y) - rect.top) / this.zoom };
    }

    mousedown_handler(e) {
        var mousePosition = this.getMousePosition(e);
        // if an object is selected, unselect it
        this.clear_selection();

        // find the object clicked in
        for (var i = 0; i < this.objects.length; i++) {
            var obj = this.objects[i];
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

    mouseup_handler(e) {
        // if an object is selected, unselect and change back the cursor
        var obj = this.selected;
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
    redraw(v) {
        // clear canvas
        // this is useful for tracking who called redraw, and how many times it is called, and when
        // console.log(`redraw=${v} id=${this.c.id}`);
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
    object_did_move(obj) { }
    object_move_finished(obj) { }
}


/* MyObject --- base object for CanvasController system */
class MyObject {
    constructor(x, y, name) {
        this.x = x;
        this.y = y;
        this.name = name;
    }
    // default - it never contains the point
    contains_point(pt) {
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
        ctx.fillText( this.name, this.x+this.r+5, this.y+this.r/2)
        ctx.restore();
    }

    contains_point(pt) {
        // return true if the point (x,y) is inside the circle
        var areaX = pt.x - this.x;
        var areaY = pt.y - this.y;
        //return true if x^2 + y^2 <= radius squared.
        var contained = areaX * areaX + areaY * areaY <= this.r * this.r;
        return contained;
    }

    // Return the location as an "x,y" string
    loc() {
        return "(" + Math.round(this.x) + "," + Math.round(this.y) + ")"
    }

}

// This contains code specific for the planttracer project.
// Create the canvas and wire up the buttons for add_marker button
class PlantTracerController extends CanvasController {
    constructor( this_id ) {
        super( `#canvas-${this_id}`, `#zoom-${this_id}` );

        this.this_id       = this_id;
        this.frame_number  = 0; // default to the first frame
        this.canvasId         = 0;
        this.movie_id        = null;             // the movie being analyzed
        this.tracked_movie_id = null;     // the id of the tracked movie
        this.video = $(`#${this.this_id} video`);

        this.video.hide();


        // add_marker_status shows error messages regarding the marker name
        this.add_marker_status = $(`#${this_id} label.add_marker_status`);

        // marker_name_input is the text field for the marker name
        this.marker_name_input = $(`#${this_id} input.marker_name_input`);
        console.log("this.marker_name_input=",this.marker_name_input);
        this.marker_name_input.on('input', (event) => { console.log('this=',this,'event=',event);this.marker_name_input_handler(event);});

        // We need to be able to enable or display the add_marker button, so we record it
        this.add_marker_button = $(`#${this_id} input.add_marker_button`);
        this.add_marker_button.on('click', (event) => { this.add_marker_onclick_handler(event);});

        // We need to be able to enable or display the
        this.track_to_end_button = $(`#${this_id} input.track_to_end`);
        this.track_to_end_button.on('click', (event) => {this.track_to_end(event);});
        this.track_to_end_button.prop('disabled',true); // disable it until we have a marker added.
    }


    // Handle keystrokes
    marker_name_input_handler (e) {
        const val = this.marker_name_input.val();
        if (val.length < MIN_MARKER_NAME_LEN) {
            this.add_marker_status.text("Marker name must be at least "+MIN_MARKER_NAME_LEN+" letters long");
            this.add_marker_button.prop('disabled',true);
            return;
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
    add_marker_onclick_handler(e) {
        if (this.marker_name_input.val().length >= MIN_MARKER_NAME_LEN) {
            this.insert_circle( 50, 50, this.marker_name_input.val());
            this.marker_name_input.val("");
        }
    }

    // available colors
    // https://sashamaps.net/docs/resources/20-colors/
    // removing green (for obvious reasons)
    circle_colors = ['#ffe119', '#4363d8', '#f58231', '#911eb4',
                     '#46f0f0', '#f032e6', '#bcf60c', '#fabebe', '#008080', '#e6beff',
                     '#9a6324', '#fffac8', '#800000', '#aaffc3', '#808000', '#ffd8b1',
                     '#000075', '#808080', '#e6194b', ]


    // add a tracking circle with the next color
    insert_circle(x, y, name) {
        // Find out how many circles there are
        let count = 0;
        for (let i=0;i<this.objects.length;i++){
            if (this.objects[i].constructor.name == myCircle.name) count+=1;
        }

        let color = this.circle_colors[count];
        this.objects.push( new myCircle(x, y, DEFAULT_R, color, color, name));

        // Generate the HTML for the table body
        let rows = '';
        for (let i=0;i<this.objects.length;i++){
            let obj = this.objects[i];
            if (obj.constructor.name == myCircle.name){
                obj.table_cell_id = "td-" + (++cell_id_counter);
                rows += `<tr>` +
                    `<td style="color:${obj.fill};text-align:center;font-size:32px;position:relative;line-height:0px;">●</td>` +
                    `<td>${obj.name}</td>` +
                    `<td id="${obj.table_cell_id}">${obj.loc()}</td><td>n/a</td><td>🚫</td></tr>`;
            }
        }
        $(`#${this.this_id} tbody.marker_table_body`).html( rows );
        this.redraw('insert_circle');

        // Finally enable the track-to-end button
        this.track_to_end_button.prop('disabled',false);
    }

    // Subclassed methods
    // Update the matrix location of the object the moved
    object_did_move(obj) {
        $( "#"+obj.table_cell_id ).text( obj.loc() );
    }

    // Movement finished; upload new annotations
    object_move_finished(obj) {
        this.put_trackpoints(this);
    }

    // Return an array of JSON trackpoints
    get_trackpoints() {
        var trackpoints = [];
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

    put_trackpoints(ptc) {
        // If we are putting the frame, we already have the frame_id
        console.log("put_trackpoints. this=",this,"ptc=",ptc);
        let put_frame_analysis_params = {
            api_key  : api_key,
            frame_id : ptc.frame_id,
            trackpoints:ptc.json_trackpoints()
        }
        console.log("put_trackpoints: ptc=",ptc,"params=",put_frame_analysis_params);
        $.post('/api/put-frame-analysis', put_frame_analysis_params ).done( (data) => {
            if (data.error) {
                alert("Error saving annotations: "+data.message);
            }
        });
    }

    /* track_to_end() is called when the 'track to end' button is clicked.
     * It tracks on the server, then displays the new movie and offers to download a CSV file.
     * Here are some pages for notes about playing the video:
     * https://www.w3schools.com/html/tryit.asp?filename=tryhtml5_video_js_prop
     * https://developer.mozilla.org/en-US/docs/Web/HTML/Element/video
     * https://developer.mozilla.org/en-US/docs/Web/Media/Audio_and_video_delivery/Video_player_styling_basics
     * https://blog.logrocket.com/creating-customizing-html5-video-player-css/
     * https://freshman.tech/custom-html5-video/
     * https://medium.com/@nathan5x/event-lifecycle-of-html-video-element-part-1-f63373c981d3
     */
    track_to_end(event) {
        // get the next frame and apply tracking logic
        console.log("track_to_end");
        const track_params = {
            api_key:api_key,
            movie_id:this.movie_id,
            frame_start:this.frame_number,
            engine_name:'CV2',
            engine_version:'1.0'
        };
        console.log("params:",track_params);
        $.post('/api/track-movie', track_params).done( (data) => {
            console.log("RECV:",data);
            this.video.show();
            let url   = `/api/get-movie-data?api_key=${api_key}&movie_id=${data.new_movie_id}`;
            this.video.html(`<source src='${url}' type='video/mp4'>`);
        });
    }

    // go to the previous frame in the tracker interface
    prev_frame(event) {
    }

    // go to the next frame in the tracker interface
    next_frame(event) {
    }

    // go to the specified frame in the tracker interface
    goto_frame(event) {
    }
}


/* myImage Object - Draws an image (x,y) specified by the url */
class myImage extends MyObject {
    constructor(x, y, url, ptc) {
        super(x, y, url)
        this.ptc = ptc;

        var theImage=this;
        this.draggable = false;
        this.ctx    = null;
        this.state  = 0;        // 0 = not loaded; 1 = loaded, first draw; 2 = loaded, subsequent draws
        this.img = new Image();

        // When the image is loaded, draw the entire stack again.
        this.img.onload = (event) => {
            theImage.state = 1;
            if (theImage.ctx) {
                ptc.redraw('myImage constructor')
            }
        }
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
        }

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
    let this_sel = `${this_id}`;
    console.log(`append_new_ptc: frame_number=${frame_number} this_id=${this_id} this_sel=${this_sel}`);

    /* Create the <div> and a new #template. Replace the current #template with the new one. */
    let div_html = div_template
        .replace('template', `${this_id}`)
        .replace('canvas-id',`canvas-${this_id}`)
        .replace('zoom-id',`zoom-${this_id}`)
        + "<div id='template'></div>";
    $( '#template' ).replaceWith( div_html );
    $( '#template' )[0].scrollIntoView(); // scrolls so that the next template slot (which is empty) is in view

    // get the request frame of the movie. When it comes back, use it to populate
    // a new PlantTracerController.
    const get_frame_parms = {
        api_key :api_key,
        movie_id:movie_id,
        frame_number:frame_number,
        format:'json',
    };
    console.log("SEND get_frame_params:",get_frame_parms);
    $.post('/api/get-frame', get_frame_parms).done( (data) => {
        console.log('RECV:',data);
        if (data.error) {
            alert(`error: ${data.message}`);
            return;
        }
        let ptc = new PlantTracerController( this_id );
        console.log(`*** this_id=${this_id} this_sel=${this_sel} data.frame_number=${data.frame_number} `);
        console.log("*** data=",data);

        // Display the photo and metadata
        ptc.objects.push( new myImage( 0, 0, data.data_url, ptc));
        ptc.movie_id       = data.movie_id;
        ptc.frame_number   = data.frame_number;
        $(`#${this_id} td.message`).text( `movie_id=${ptc.movie_id} frame_number=${ptc.frame_number} ` );

        // Add points in the analysis
        if (data.analysis) {
            console.log("analysis:",data.analysis);
            for (let ana of data.analysis) {
                console.log("ana:",ana)
                for (let pt of ana.annotations) {
                    console.log("pt:",pt);
                    ptc.insert_circle( pt['x'], pt['y'], pt['label'] );
                }
            }
        }
        //
        if (data.trackpoints_engine) {
            for (let tp of data.trackpoints_engine) {
                ptc.insert_circle( tp['x'], tp['y'], tp['label'] );
            }
        } else if (data.trackpoints) {
            for (let tp of data.trackpoints) {

                ptc.insert_circle( tp['x'], tp['y'], tp['label'] );
            }
        }
        ptc.redraw('append_new_ptc');              // initial drawing
    });
}

// Called when the page is loaded
function analyze_movie() {

    // Say which movie we are working on
    $('#firsth2').html(`Movie ${movie_id}`);

    // capture the HTML of the <div id='#template'> into a new div
    div_template = "<div id='template'>" + $('#template').html() + "</div>";

    // erase the template div's contents, leaving an empty template at the end
    $('#template').html('');

    ptc = append_new_ptc(movie_id, 0);           // create the first <div> and its controller
    // Prime by loading the first frame of the movie.
    // Initial drawing
}
