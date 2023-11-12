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

/* MyCanvas Object - creates a canvas that can manage MyObjects */

class MyCanvas {
    constructor(html_id) {      // html_id is where this canvas gets inserted
        const canvas_id = html_id + "-canvas";
        $(html_id).html(`canvas: <canvas id='${canvas_id}' width="${DEFAULT_WIDTH}" height="${DEFAULT_HEIGHT}"></canvas>`);
        this.c = document.getElementById( canvas_id );
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

    mouseup_handler(e) {
        // if an object is selected, unselect and change back the cursor
        this.clear_selection();
        this.c.style.cursor='auto';
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

    }
    // TODO: might want to hilight entered object here.

    // Main drawing function:
    redraw() {
        // clear canvas
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
}


/* MyObject --- base object for MyCanvas system */
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

// This contains code specific for the planttracer project
class MyPlantTracerCanvas extends MyCanvas {
    mousemove_handler(e) {
        super.mousemove_handler(e);

        // Update the matrix location if anything is registered
        if (this.selected) {
            $( "#"+this.selected.table_cell_id ).text( this.selected.loc() );
        }
    }

    registerAddRow(marker_name_field_id, add_marker_button_id, add_marker_status_id) {
        var me=this;
        $('#'+marker_name_field_id).on('input',function(e) { me.marker_name_input_handler(e);});
        this.add_marker_button = $('#'+add_marker_button_id);
        this.add_marker_status = $('#'+add_marker_status_id);
        this.add_marker_button.on('click',function(e){me.add_marker_onclick_handler(e);});
    }

    marker_name_input_handler (e) {
        const val = $('#marker-name-field').val();
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


    add_marker_onclick_handler(e) {
        this.add_circle( 50, 50, $('#marker-name-field').val());
    }

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
            if (this.objects[i].constructor.name == 'myCircle') count+=1;
        }

        let color = this.circle_colors[count];
        this.objects.push( new myCircle(x, y, DEFAULT_R, color, color, name));

        // Generate the HTML for the table body
        let rows = '';
        for (let i=0;i<this.objects.length;i++){
            let obj = this.objects[i];
            if (obj.constructor.name == 'myCircle'){
                obj.table_cell_id = `loc-${i}`
                rows += `<tr><td style="color:${obj.fill};text-align:center;font-size:32px;position:relative;line-height:0px;">●</td><td>${obj.name}</td>` +
                    `<td id="${obj.table_cell_id}">${obj.loc()}</td><td>n/a</td></tr>`;
            }
        }
        $('#marker-tbody').html( rows );
        this.redraw();
    }
}


/* myImage Object - Draws an image (x,y) specified by the url */

class myImage extends MyObject {
    constructor(x, y, url, mptc) {
        super(x, y, url)
        this.mptc = mptc;

        var theImage=this;
        this.draggable = false;
        this.ctx = null;
        this.img = new Image();

        // When the image is loaded, draw the entire stack again.
        this.img.onload = function() {
            if (theImage.ctx) {
                mptc.redraw()
            }
        }
        this.draw = function (ctx) {
            theImage.ctx = ctx;
            ctx.drawImage(this.img, 0, 0);
        }

        // set the URL. It loads immediately if it is a here document.
        this.img.src = url;
    }
}



////////////////////////////////////////////////////////////////
// Drag control


// Called when the page is loaded
function analyze_movie() {

    // Say which movie it is and load the first frame
    $('#firsth2').html(`Movie ${movie_id}`);
    mptc = new MyPlantTracerCanvas('#frame1');
    mptc.registerAddRow('marker-name-field', 'add-marker-button','add-marker-status');

    $.post('/api/get-frame', {movie_id:movie_id, api_key:api_key, frame_msec:0, msec_delta:0, format:'json', analysis:true})
        .done( function(data) {
            data = JSON.parse(data); // convert to JSON
            mptc.objects.push( new myImage( 0, 0, data.data_url, mptc));
            setTimeout( function() {mptc.redraw()}, 10); // trigger a reload at 1 second just in case.
            //setTimeout( draw, 1000); // trigger a reload at 1 second just in case.
        });


    // For testing, just add two circles
    // add_circle( 50, 50, "first");
    // add_circle( 25, 25, "second");

    // Initial drawing
    mptc.redraw();

    // And add the event listeners
    // Should this be redone with the jQuery event system
}
