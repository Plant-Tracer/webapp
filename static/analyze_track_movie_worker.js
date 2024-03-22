/* jshint esversion: 8 */
// code for /analyze web worker
// - actually track and return the response

// JQuery not available in webworker because there is no document
// https://stackoverflow.com/questions/48408491/using-webworkers-jquery-returns-undefined

onmessage = function(e) {
    console.log("analyze_track_movie_worker.js. e=",e);
    const obj = e.data;
    const formData = new FormData();
    for (const [key, value] of Object.entries(e.data)){
        formData.append(key, value);
    }
    fetch('/api/track-movie', {
        method:'POST',
        body: formData
    })
        .then((response) => response.json())
        .then((data) => postMessage(data));
};
