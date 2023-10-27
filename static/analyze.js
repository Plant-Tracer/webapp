// code for /analyze


function analyze_movie() {
    // Say which movie it is and load it
    $('#firsth2').html(`Movie ${movie_id}`);
    let url = `/api/get-frame?movie_id=${movie_id}&api_key=${api_key}`;
    $('#frame_data').html(`<img src='${url}'/>`);
}
