// code for /analyze

function frame0_loaded(elem) {
    console.log('image loaded. setting up mouse movement');
    $('#frame0').mousemove(function(event){
        var e = jQuery.Event(event);
        console.log("image mousemove x= y=",event.originalEvent.clientX,event.originalEvent.clientY);
        console.log("  e=",e,"client (x,y)=",e.clientX,e.clientY," offset(x,y)=",e.offsetX,e.offsetY);
        // e.offsetX/Y are coordinates within the image

    });
}

console.log("analyze.js");
function analyze_movie() {
    // Say which movie it is and load the first frame
    $('#firsth2').html(`Movie ${movie_id}`);
    let url = `/api/get-frame?movie_id=${movie_id}&api_key=${api_key}&frame_msec=0&msec_delta=0`;
    console.log("url=",url);
    $('#frame_data').html(`<img id='frame0' src=${url} onload='frame0_loaded(this)'>`);
}
