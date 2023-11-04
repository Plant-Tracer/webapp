// code for /analyze

// See ideas from:
// https://stackoverflow.com/questions/3768565/drawing-an-svg-file-on-a-html5-canvas
// https://www.html5canvastutorials.com/tutorials/html5-canvas-circles/
// a bit more object oriented, but not massively so

const DEFAULT_R = 10;

// The globals that we need
var globals = {
    c:null,                     // the canvas
    ctx:null,                   // the context
    selected:null,               // the selected object
    objects: []                // the objects
};

/* myCircle Object - Draws a circle radius (r) at (x,y) with fill and stroke colors
 */

class myObject {
    constructor(x, y, name) {
        this.x = x;
        this.y = y;
        this.name = name;
    }
    selected() {
        return this == globals.selected;
    }
    // default - it never contains the point
    contains_point(pt) {
        return false;
    }
}

class myCircle extends myObject {
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

    draw(ctx) {
        ctx.save();
        ctx.globalAlpha = 0.5;
        if (this != globals.selected) {
            // If we are selected, the cursor is cross-hair.
            // If we are not selected, we need to draw the cross-hair
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

/* myImage Object - Draws an image (x,y) specified by the url */

class myImage extends myObject {
    constructor(x,y,url) {
        super(x, y, url)

        var theImage=this;
        this.draggable = false;
        this.ctx = null;
        this.img = new Image();
        this.img.src = url;
        this.draw = function (ctx) {
            theImage.ctx = ctx;
            ctx.drawImage(this.img, 0, 0);
        }

        // When the image is loaded, draw the entire stack again.
        this.img.onload = function() {
            if (theImage.ctx) {
                draw( theImage.ctx );
            }
        }
    }
}

// https://sashamaps.net/docs/resources/20-colors/
// removing green (for obvious reasons)
circle_colors = ['#e6194b', '#ffe119', '#4363d8', '#f58231', '#911eb4',
                 '#46f0f0', '#f032e6', '#bcf60c', '#fabebe', '#008080', '#e6beff',
                 '#9a6324', '#fffac8', '#800000', '#aaffc3', '#808000', '#ffd8b1', '#000075', '#808080']

// add a circle with the next color
function add_circle(x, y, name) {
    // Find out how many circles there are
    let count = 0;
    for (let i=0;i<globals.objects.length;i++){
        if (globals.objects[i].constructor.name == 'myCircle') count+=1;
    }
    let color = circle_colors[count];
    globals.objects.push( new myCircle(x, y, DEFAULT_R, color, color, name));

    // Generate the HTML for the table body
    let rows = '';
    for (let i=0;i<globals.objects.length;i++){
        let obj = globals.objects[i];
        if (obj.constructor.name == 'myCircle'){
            obj.id = `loc-${i}`
            rows += `<tr><td style="color:${obj.fill};text-align:center;font-size:32px;position:relative;line-height:0px;">●</td><td>${obj.name}</td><td id="${obj.id}">${obj.loc()}</td><td>n/a</td></tr>`;
        }
    }
    $('#marker-tbody').html( rows );
    draw();
}

// main draw method
function draw( ) {
    // clear canvas
    globals.ctx.clearRect(0, 0, globals.c.width, globals.c.height);

    // draw the objects. Always draw the selected objects after  the unselected (so they are on top)
    for (let s = 0; s<2; s++){
        for (let i = 0; i< globals.objects.length; i++){
            let obj = globals.objects[i];
            if ((s==0 && !obj.selected()) || (s==1 && obj.selected())) {
                obj.draw( globals.ctx );
            }
        }
    }
}

////////////////////////////////////////////////////////////////
// Drag control

var isMouseDown = false;        // is the mouse down
var focused = {
    key: null,                  // the object being dragged
    state: false
}


function getMousePosition(e) {
    var rect = globals.c.getBoundingClientRect();
    return { x: Math.round(e.x) - rect.left,
             y: Math.round(e.y) - rect.top };
    return { x: Math.max(0,Math.max(e.x - rect.left, rect.left)),
             y: Math.max(0,Math.min(e.y - rect.top, rect.top)) };
}

function mouseMoved(e) {
    if (!globals.selected) {
        return;
    }
    var mousePosition = getMousePosition(e);

    // update position
    if (globals.selected) {
        // Update the position in the image
        globals.selected.x = mousePosition.x;
        globals.selected.y = mousePosition.y;
        draw();

        // Update the matrix
        $( "#"+globals.selected.id ).text( globals.selected.loc() );

        return;
    }
    // TODO: might want to hilight entered object here.
}

function clear_selection() {
    if (globals.selected) {
        globals.selected = null;
    }
}


// set mousedown state
function mouseChanged(e) {
    var mousePosition = getMousePosition(e);
    if (e.type === "mousedown") {
        // if an object is selected, unselect it
        clear_selection();


        // find the object clicked in
        for (var i = 0; i < globals.objects.length; i++) {
            var obj = globals.objects[i];
            if (obj.draggable && obj.contains_point( mousePosition)) {
                globals.selected = obj;
                // change the cursor to crosshair if something is selected
                globals.c.style.cursor='crosshair';
            }
        }
    }
    if (e.type == 'mouseup') {
        // if an object is selected, unselect and change back the cursor
        clear_selection();
        globals.c.style.cursor='auto';
    }
    draw();
}

function add_marker_clicked() {
}

function done_button_clicked() {
}

const MIN_MARKER_NAME_LEN = 5;
function marker_name_input(e) {
    let   but = $('#add-marker-button');
    let   stat = $('#marker-status');
    const val = $('#marker-name').val();
    if (val.length < MIN_MARKER_NAME_LEN) {
        stat.text("Marker name must be at least "+MIN_MARKER_NAME_LEN+" letters long");
        but.prop('disabled',true);
        return;
    }
    // Make sure it isn't in use
    for (let i=0;i<globals.objects.length; i++){
        if(globals.objects[i].name == val){
            stat.text("That name is in use, choose another.");
            but.prop('disabled',true);
            return;
        }
    }
    stat.text('');
    but.prop('disabled',false);
}

// Called when the page is loaded
function analyze_movie() {

    // Say which movie it is and load the first frame
    $('#firsth2').html(`Movie ${movie_id}`);

    // URL of the first frame in the movie
    const url = `/api/get-frame?movie_id=${movie_id}&api_key=${api_key}&frame_msec=0&msec_delta=0`;

    // The canvas is defined int he template
    globals.c   = document.getElementById('c1'); // get the canvas
    globals.ctx = globals.c.getContext('2d');          // get the 2d drawing context

    // Make sure the array is empty.
    while (globals.objects.length > 0){
        globals.objects.pop();
    }
    // Create the objects. Draw order is insertion order.
    // Image first means that the circles go on top
    globals.objects.push( new myImage( 0, 0, url ));

    // For testing, just add two circles
    add_circle( 50, 50, "first");
    add_circle( 25, 25, "second");

    // Initial drawing
    draw();

    // And add the event listeners
    // Should this be redone with the jQuery event system
    globals.c.addEventListener('mousemove', mouseMoved, false);
    globals.c.addEventListener('mousedown', mouseChanged, false);
    globals.c.addEventListener('mouseup', mouseChanged, false);
}
