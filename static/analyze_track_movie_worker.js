/* jshint esversion: 8 */
// code for /analyze web worker
// - actually track and return the response

// JQuery not available in webworker because there is no document
// https://stackoverflow.com/questions/48408491/using-webworkers-jquery-returns-undefined

onmessage = function(e) {
    console.log("analyze_track_movie_workerr.js. e=",e);
    $.post('/api/track-movie', e.data).done( (data) => {
        if (data.error) {
            this.tracked_movie_status.text("Tracking error: "+data.message);
        } else {
            postMessage(data);
        }
    });
};
