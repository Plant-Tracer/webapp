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
- Pressing 'track next frame' loads the next frame under the current frame, but the annotations come from applying the tracking API to the current anotations.
- Pressing 'track next 10 frames' does the same, but for 10 frames.


***/

const DEFAULT_R = 10;           // default radius of the marker
const DEFAULT_FRAMES = 20;      // default number of frames to show
const DEFAULT_WIDTH = 340;
const DEFAULT_HEIGHT= 340;
const MIN_MARKER_NAME_LEN = 5;  // markers must be this long

/* MyCanvas Object - creates a canvas that can manage MyObjects */

var cell_id_counter = 0;
var div_id_counter  = 0;
var template_html   = null;

class CanvasController {
    constructor(canvas_selector) {      // html_id is where this canvas gets inserted
        // const canvas_id = html_id + "-canvas";
        // $(html_id).html(`canvas: <canvas id='${canvas_id}' width="${DEFAULT_WIDTH}" height="${DEFAULT_HEIGHT}"></canvas>`);

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

        // Register my events.
        // We need to wrap them in lambdas and copy 'this' to 'me' because when the event triggers,
        // 'this' points to the HTML element that generated the event.
        // This took me several hours to figure out.
        var me=this;
        this.c.addEventListener('mousemove', function(e) {me.mousemove_handler(e);} , false);
        this.c.addEventListener('mousedown', function(e) {me.mousedown_handler(e);} , false);
        this.c.addEventListener('mouseup',   function(e) {me.mouseup_handler(e);}, false);
    }

    // Selection Management
    clear_selection() {
        if (this.selected) {
            this.selected = null;
        }
    }

    getMousePosition(e) {
        var rect = this.c.getBoundingClientRect();
        return { x: Math.round(e.x) - rect.left,
                 y: Math.round(e.y) - rect.top };
        return { x: Math.max(0,Math.max(e.x - rect.left, rect.left)),
                 y: Math.max(0,Math.min(e.y - rect.top, rect.top)) };
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
        this.redraw();
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
        this.redraw();
        this.object_did_move(this.selected);
    }

    mouseup_handler(e) {
        // if an object is selected, unselect and change back the cursor
        var obj = this.selected;
        this.clear_selection();
        this.c.style.cursor='auto';
        this.redraw();
        this.object_move_finished(obj);
    }

    // Main drawing function:
    redraw(v) {
        // clear canvas
        console.log("redraw=",v);
        this.ctx.clearRect(0, 0, this.c.width, this.c.height);

        // draw the objects. Always draw the selected objects after  the unselected (so they are on top)
        for (let s = 0; s<2; s++){
            for (let i = 0; i< this.objects.length; i++){
                let obj = this.objects[i];
                if ((s==0 && this.selected!=obj) || (s==1 && this.selected==obj)){
                    obj.draw( this.ctx , this.selected==obj);
                }
            }
        }
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
        self.name = name;
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
        super( `#canvas-${this_id}` );

        var me=this;            // record me, becuase this is overridden when the functions below execute
        this.this_id      = this_id;
        this.frame_msec   = null; // don't know it yet, but I will
        this.canvasId     = 0;

        // add_marker_status shows error messages regarding the marker name
        this.add_marker_status = $(`#${this_id} label.add_marker_status`);

        // marker_name_input is the text field for the marker name
        this.marker_name_input = $(`#${this_id} input.marker_name_input`);
        this.marker_name_input.on('input',function(e) { me.marker_name_input_handler(e);});

        // We need to be able to enable or display the add_marker button, so we record it
        this.add_marker_button = $(`#${this_id} input.add_marker_button`);
        this.add_marker_button.on('click',function(e) { me.add_marker_onclick_handler(e);});

        // Wire up the rest
        $(`#${this_id}  input.track_next_frame_button`).on('click', function(e) {me.track_next_frame(e);});
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
        this.add_circle( 50, 50, this.marker_name_input.val());
        this.marker_name_input.val("");
    }

    // available colors
    // https://sashamaps.net/docs/resources/20-colors/
    // removing green (for obvious reasons)
    circle_colors = ['#ffe119', '#4363d8', '#f58231', '#911eb4',
                     '#46f0f0', '#f032e6', '#bcf60c', '#fabebe', '#008080', '#e6beff',
                     '#9a6324', '#fffac8', '#800000', '#aaffc3', '#808000', '#ffd8b1', '#000075', '#808080', '#e6194b', ]


    // add a tracking circle with the next color
    add_circle(x, y, name) {
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
                obj.table_cell_id = ++cell_id_counter;
                rows += `<tr><td style="color:${obj.fill};text-align:center;font-size:32px;position:relative;line-height:0px;">●</td><td>${obj.name}</td>` +
                    `<td id="${obj.table_cell_id}">${obj.loc()}</td><td>n/a</td></tr>`;
            }
        }
        $(`#${this.this_id} tbody.marker_table_body`).html( rows );
        this.redraw(0);
    }

    // Subclassed methods
    // Update the matrix location of the object the moved
    object_did_move(obj) {
        $( "#"+obj.table_cell_id ).text( obj.loc() );
    }

    // Movement finished; upload new annotations
    object_move_finished(obj) {
        this.put_frame_analysis();
    }

    put_frame_analysis() {
        var annotations = [];
        for (let i=0;i<this.objects.length;i++){
            let obj = this.objects[i];
            if (obj.constructor.name == myCircle.name){
                annotations.push( {x:obj.x, y:obj.y, name:obj.name} );
            }
        }
        console.log("annotations:",annotations);

        $.post('/api/put-frame-analysis', {frame_id:this.frame_id,
                                           api_key:api_key,
                                           engine_name:'MANUAL',
                                           engine_version:'1',
                                           annotations:JSON.stringify(annotations)})
            .done( function(data) {
                console.log("response for put-frame-analysis:",data);
                if (data['error']) {
                    alert("Error saving annotations: "+data);
                }
            });
    }

    // Request the next frame if we don't have it.
    // If we do, track it.
    track_next_frame() {
        console.log(`track_next_frame. msec=${this.frame_msec}`);
        create_new_div(this.frame_msec, +1); // get the next one
    }
}


/* myImage Object - Draws an image (x,y) specified by the url */
class myImage extends MyObject {
    constructor(x, y, url, ptc) {
        super(x, y, url)
        this.ptc = ptc;

        var theImage=this;
        this.draggable = false;
        this.ctx = null;
        this.img = new Image();

        // When the image is loaded, draw the entire stack again.
        this.img.onload = function() {
            if (theImage.ctx) {
                ptc.redraw(1)
            }
        }
        this.draw = function (ctx) {
            theImage.ctx = ctx;
            ctx.drawImage(this.img, 0, 0);
            console.log("drew image");
        }

        // set the URL. It loads immediately if it is a here document.
        this.img.src = url;
    }
}


// Creates a new analysis div
function create_new_div(frame_msec, msec_delta) {
    let this_id  = div_id_counter++;
    let this_sel = `#${this_id}`;
    console.log("create_new_div this_id=",this_id,"this_sel=",this_sel);

    let div_html = div_template
        .replace('template', `${this_id}`)
        .replace('<canvas ',`<canvas id='canvas-${this_id}' `)
        + "<div id='template'></div>";
    //console.log("div_html=",div_html);
    $( '#template' ).replaceWith( div_html );

    console.log("create new ptc");
    let ptc = new PlantTracerController( this_id );    // create a new PlantTracerController; we may need to save it in an array too
    $.post('/api/get-frame', {movie_id:movie_id,
                              api_key:api_key,
                              frame_msec:frame_msec,
                              msec_delta:msec_delta,
                              format:'json',
                              analysis:true})
        .done( function(json_value) {
            // We got data back consisting of the frame, frame_id, frame_msec and more...
            data = JSON.parse(json_value);
            ptc.objects.push( new myImage( 0, 0, data.data_url, ptc));
            ptc.frame_id       = data.frame_id;
            ptc.frame_msec     = data.frame_msec;
            $(`#${this_id} td.message`).text(`Frame msec=${ptc.frame_msec} `);
            setTimeout( function() {ptc.redraw(2)}, 10); // trigger a reload at 1 second just in case.
        });
    ptc.redraw(3);               // initial drawing
    return ptc;
}

// Called when the page is loaded
function analyze_movie() {

    // Say which movie we are working on
    $('#firsth2').html(`Movie ${movie_id}`);

    // capture the HTML of the <div id='#template'> into a new div
    div_template = "<div id='template'>" + $('#template').html() + "</div>";

    // erase the template div's contents, leaving an empty template at the end
    $('#template').html('');

    ptc = create_new_div(0, 0);           // create the first <div> and its controller

    // Prime by loading the first frame of the movie.
    // Initial drawing
}
