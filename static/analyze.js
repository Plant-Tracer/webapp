// code for /analyze

// See ideas from:
// https://stackoverflow.com/questions/3768565/drawing-an-svg-file-on-a-html5-canvas
// https://www.html5canvastutorials.com/tutorials/html5-canvas-circles/
// a bit more object oriented, but not massively so

const DEFAULT_R = 10;           // default radius of the marker
const DEFAULT_FRAMES = 20;      // default number of frames to show
const DEFAULT_WIDTH = 340;
const DEFAULT_HEIGHT= 340;
const MIN_MARKER_NAME_LEN = 5;  // markers must be this long

/* MyCanvasController Object - creates a canvas that can manage MyObjects */

var id_counter = 0;

class MyCanvasController {
    constructor(canvas_selector, zoom_selector) {      // html_id is where this canvas gets inserted
        let canvas = $( canvas_selector );
        this.c   = canvas[0];     // get the element

        //this.c = document.getElementById( 'canvas-1' );
        this.ctx = this.c.getContext('2d');                  // the drawing context

        this.selected = null,             // the selected object
        this.objects = [];                // the objects
        this.zoom    = 1;                 // default zoom

        // Register my events.
        // We need to wrap them in lambdas and copy 'this' to 'me' because when the event triggers,
        // 'this' points to the HTML element that generated the event.
        // This took me several hours to figure out.
        var me=this;
        this.c.addEventListener('mousemove', function(e) {me.mousemove_handler(e);} , false);
        this.c.addEventListener('mousedown', function(e) {me.mousedown_handler(e);} , false);
        this.c.addEventListener('mouseup',   function(e) {me.mouseup_handler(e);}, false);
        // Catch the zoom change event
        let s=$(zoom_selector);
        s.on('change', function() {
            me.set_zoom( $(this).val() / 100 );
        });
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

    set_zoom(factor) {
        this.zoom = factor;
        this.c.width = this.naturalWidth * factor;
        this.c.height = this.naturalHeight * factor;
        this.redraw();
    }

    // Main drawing function:
    redraw() {
        // clear canvas
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


/* MyObject --- base object for MyCanvasController system */
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
class MyPlantTracerCanvas extends MyCanvasController {
    constructor( div_selector ) {
        super( div_selector + ' canvas', div_selector + ' .zoom' );

        var me=this;
        this.div_selector = div_selector;
        this.marker_form       = $(div_selector + ' form.marker_form');
        this.marker_name_input = $(div_selector + ' input.marker_name_input');
        this.add_marker_button = $(div_selector + ' input.add_marker_button');
        this.add_marker_status = $(div_selector + ' label.add_marker_status');

        this.marker_name_input.on('input',function(e) { me.marker_name_input_handler(e);});
        this.add_marker_button.on('click',function(e) { me.add_marker_onclick_handler(e);});
        this.marker_form.on('submit',function(e)      { me.add_marker_onclick_handler(e);e.preventDefault();});
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
            this.add_circle( 50, 50, this.marker_name_input.val());
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
                obj.table_cell_id = ++id_counter;
                rows += `<tr><td style="color:${obj.fill};text-align:center;font-size:32px;position:relative;line-height:0px;">●</td><td>${obj.name}</td>` +
                    `<td id="${obj.table_cell_id}">${obj.loc()}</td><td>n/a</td></tr>`;
            }
        }
        $(this.div_selector + ' tbody.marker_table_body').html( rows );
        this.redraw();
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
        $.post('/api/put-frame-analysis', {frame_id:this.frame_id,
                                           api_key:api_key,
                                           engine_name:'MANUAL',
                                           engine_version:'1',
                                           annotations:JSON.stringify(annotations)})
            .done( function(data) {
                if (data['error']) {
                    alert("Error saving annotations: "+data);
                }
            });
    }
}


/* myImage Object - Draws an image (x,y) specified by the url */

class myImage extends MyObject {
    constructor(x, y, url, mptc) {
        super(x, y, url)
        this.mptc = mptc;

        var theImage=this;
        this.draggable = false;
        this.ctx    = null;
        this.state  = 0;        // 0 = not loaded; 1 = loaded, first draw; 2 = loaded, subsequent draws
        this.img = new Image();

        // When the image is loaded, draw the entire stack again.
        this.img.onload = function() {
            theImage.state = 1;
            if (theImage.ctx) {
                mptc.redraw()
            }
        }
        this.draw = function (ctx) {
            // See if this is the first time we have drawn in the context.
            // If so,
            theImage.ctx = ctx;
            if (theImage.state > 0){
                if (theImage.state==1){
                    mptc.naturalWidth  = this.img.naturalWidth;
                    mptc.naturalHeight = this.img.naturalHeight;
                    theImage.state=2;
                    mptc.set_zoom( 1.0 );
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



////////////////////////////////////////////////////////////////
// Drag control


// Called when the page is loaded
function analyze_movie() {

    // Say which movie it is and load the first frame
    $('#firsth2').html(`Movie ${movie_id}`);
    mptc = new MyPlantTracerCanvas('#template');

    $.post('/api/get-frame', {movie_id:movie_id, api_key:api_key, frame_msec:0, msec_delta:0, format:'json', analysis:true})
        .done( function(data) {
            data = JSON.parse(data); // convert to JSON
            mptc.objects.push( new myImage( 0, 0, data.data_url, mptc));
            mptc.frame_id = data.frame_id;
            setTimeout( function() {mptc.redraw()}, 10); // trigger a reload at 1 second just in case.
        });


    // Initial drawing
    mptc.redraw();
}
