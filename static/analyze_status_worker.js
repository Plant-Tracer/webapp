"use strict";
/* jshint esversion: 8 */
// code for /analyze web worker


// JQuery not available in webworker because there is no document
// https://stackoverflow.com/questions/48408491/using-webworkers-jquery-returns-undefined

const NOTIFY_UPDATE_INTERVAL = 1000;    // how quickly to pool for retracking (in msec)

// Set a timer to get the movie status from the server and put it in the status field
// during long operations.
// See https://developer.mozilla.org/en-US/docs/Web/API/setInterval
function start_update_timer(obj) {
    setInterval( () => {
        console.log(Date.now(),"update_tracked_movie_status_from_server obj=",obj);
        const formData = new FormData();
        formData.append('api_key',obj.api_key);
        formData.append('movie_id',obj.movie_id);
        fetch('/api/get-movie-metadata', {
            method:'POST',
            body: formData
        })
            .then((response) => response.json())
            .then((data) => {
                console.log(Date.now(),"get-movie-metadata (movie_id=",obj.movie_id,") got = ",data,"metadata:",data.metadata,"status:",data.metadata.status);
                if (data.error==false){
                    // Send the status back to the UX
                    postMessage(data.metadata);
                }
            })
    },NOTIFY_UPDATE_INTERVAL);
}

onmessage = function(e) {
    console.log("load analyze_webworker.js. e=",e);
    start_update_timer(e.data);
};
