// code for /analyze

// See ideas from:
// https://stackoverflow.com/questions/3768565/drawing-an-svg-file-on-a-html5-canvas
// https://www.html5canvastutorials.com/tutorials/html5-canvas-circles/
// a bit more object oriented, but not massively so

// The globals that we need
var globals = {
    c:null,                     // the canvas
    ctx:null,                   // the context
    selected:null,               // the selected object
    objects: []                // the objects
};

/* myCircle Object - Draws a circle radius (r) at (x,y) with fill and stroke colors
 */
function myCircle(x, y, r, fill, stroke, name) {
    this.startingAngle = 0;
    this.endAngle = 2 * Math.PI;
    this.x = x;
    this.y = y;
    this.r = r;
    this.name = name;
    this.draggable = true;

    this.fill = fill;
    this.stroke = stroke;

    this.draw = function (ctx) {
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.r, this.startingAngle, this.endAngle);
        ctx.fillStyle = this.fill;
        ctx.lineWidth = 3;
        ctx.fill();
        ctx.strokeStyle = this.stroke;
        ctx.stroke();
    }

    this.contains_point = function( pt) {
        // return true if the point (x,y) is inside the circle
        var areaX = pt.x - this.x;
        var areaY = pt.y - this.y;
        //return true if x^2 + y^2 <= radius squared.
        console.log("pt.x=",pt.x,"pt.y=",pt.y,"this.x=",this.x,"this.y=",this.y,"areaX=",areaX,"areaY=",areaY,"this.r=",this.r);
        var contained = areaX * areaX + areaY * areaY <= this.r * this.r;
        console.log("v1=", areaX * areaX + areaY * areaY , "contained=",contained);
        return contained;
    }
}

/* myImage Object - Draws an image (x,y) specified by the url */

function myImage(x,y,url) {
    var theImage=this;
    this.x = x;
    this.y = y;
    this.draggable = false;
    this.ctx = null;
    this.img = new Image();
    this.img.src = url;
    this.draw = function (ctx) {
        console.log("img.draw");
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

// main draw method
function draw( ) {
    // clear canvas
    globals.ctx.clearRect(0, 0, globals.c.width, globals.c.height);

    // draw the objects
    for (var i = 0; i< globals.objects.length; i++){
        globals.objects[i].draw( globals.ctx );
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
    return { x: e.x - rect.left,
             y: e.y - rect.top };
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
        globals.selected.x = mousePosition.x;
        globals.selected.y = mousePosition.y;
        draw();
        return;
    }
    // TODO: might want to hilight entered object here.
}

function clear_selection() {
    if (globals.selected) {
        globals.selected.selected = false;
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
            console.log("checking ",obj.name);
            if (obj.draggable && obj.contains_point( mousePosition)) {
                globals.selected = obj;
                globals.selected.selected = true;
            }
        }
        draw();
    }
    if (e.type == 'mouseup') {
        // if an object is selected, unselect
        clear_selection();
    }
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
    //globals.objects.push( new myImage( 0, 0, url ));
    globals.objects.push( new myCircle(50, 50, 10, "red", "white", "red ball"));
    globals.objects.push( new myCircle(10, 50, 10, "blue", "white", "blue ball"));

    // Initial drawing
    draw();

    // And add the event listeners
    // Should this be redone with the jQuery event system
    globals.c.addEventListener('mousemove', mouseMoved, false);
    globals.c.addEventListener('mousedown', mouseChanged, false);
    globals.c.addEventListener('mouseup', mouseChanged, false);


}
