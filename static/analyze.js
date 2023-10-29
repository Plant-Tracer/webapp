// code for /analyze

// See ideas from:
// https://stackoverflow.com/questions/3768565/drawing-an-svg-file-on-a-html5-canvas
// https://www.html5canvastutorials.com/tutorials/html5-canvas-circles/

// The objects we will draw
var objects = [];

/* myCircle Object - Draws a circle radius (r) at (x,y) with fill and stroke colors
 */
function myCircle(x, y, r, fill, stroke) {
    this.startingAngle = 0;
    this.endAngle = 2 * Math.PI;
    this.x = x;
    this.y = y;
    this.r = r;

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
}

/* myImage Object - Draws an image (x,y) specified by the url */

function myImage(x,y,url) {
    var theImage=this;
    this.x = x;
    this.y = y;
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
function draw( ctx ) {
    // clear canvas
    ctx.clearRect(0, 0, ctx.width, ctx.height);
    // draw the objects
    for (var i = 0; i< objects.length; i++){
        objects[i].draw(ctx);
    }
}



// Called when the page is loaded
function analyze_movie() {

    // Say which movie it is and load the first frame
    $('#firsth2').html(`Movie ${movie_id}`);

    // URL of the first frame in the movie
    const url = `/api/get-frame?movie_id=${movie_id}&api_key=${api_key}&frame_msec=0&msec_delta=0`;

    // The canvas is defined int he template
    var c = document.getElementById('c1'); // get the canvas
    console.log("c=",c);
    var ctx = c.getContext('2d');          // get the 2d drawing context
    console.log("ctx=",ctx);

    // Make sure the array is empty.
    while (objects.length > 0){
        objects.pop();
    }
    // Create the objects. Draw order is insertion order.
    objects.push( new myImage( 0, 0, url ));
    objects.push( new myCircle(50, 50, 5, "red", "white"));
    objects.push( new myCircle(10, 50, 5, "blue", "white"));

    draw(ctx);
}
