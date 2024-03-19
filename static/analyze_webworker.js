/* jshint esversion: 8 */
// code for /analyze web worker
/* global window_ptc */

// JQuery not available in webworker because there is no document
// https://stackoverflow.com/questions/48408491/using-webworkers-jquery-returns-undefined

const NOTIFY_UPDATE_INTERVAL = 5000;    // how quickly to pool for retracking (in msec)

// Update the status from the server - migrate to a web worker.*** TODO*&
function update_tracked_movie_status_from_server(movie_id) {
    console.log(Date.now(),"update_tracked_movie_status_from_server movie_id=",movie_id);
    //window_ptc.tracked_movie_status.text("Getting Movie Metadata...");
    return;
//    $.post('/api/get-movie-metadata', {api_key:api_key, movie_id:movie_id}).done( (data) => {
//        console.log(Date.now(),"got = ",data);
//        if (data.error==false){
//            this.tracked_movie_status.text(data.metadata.status);
//        }
//    });
}


// Set a timer to get the movie status from the server and put it in the status field
// during long operations.
// See https://developer.mozilla.org/en-US/docs/Web/API/setInterval
function start_update_timer(movie_id) {
    //    window_ptc.status_interval_id =
    setInterval( () => {
        this.update_tracked_movie_status_from_server(movie_id);
    }, NOTIFY_UPDATE_INTERVAL);
}

function stop_update_timer() {
    clearInterval(this.status_interval_id);
    window_ptc.status_interval_id = undefined;
}

onmessage = function(e) {
    console.log("load analyze_webworker.js. e=",e);
    start_update_timer(e.data);
}
