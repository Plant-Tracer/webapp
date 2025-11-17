"use strict";

//code for /analyze

/* eslint-env es6 */
/* eslint parserOptions: { "sourceType": "module" } */

/* jshint esversion: 8 */
/*global api_key,movie_id,API_BASE,STATIC_BASE,URL */
/*global console,alert */

/*
 * Tracer Controller:
 * Manages the table of markers and tracing the movie as requested by the user.
 *
 */

const MARKER_RADIUS = 10;           // default radius of the marker
const RULER_MARKER_COLOR = 'orange';
const PLANT_MARKER_COLOR = 'red';
const MIN_MARKER_NAME_LEN = 4;  // markers must be this long (allows 'apex')
const ENGINE = 'CV2';
const ENGINE_VERSION = '1.0';
const TRACKING_COMPLETED_FLAG='TRACKING COMPLETED';
const ADD_MARKER_STATUS_TEXT="Drag each marker to the appropriate place on the image. You can also create additional markers."
const TRACKING_POLL_MSEC=1000;
const RETRACK_MOVIE='Retrace movie';
const MAX_FRAMES = 1000000;

var cell_id_counter = 0;
var div_id_counter  = 0;
var div_template = '';          // will be set with the div template

import { CanvasController, CanvasItem, Marker, WebImage, Line } from "./canvas_controller.mjs";
import { MovieController } from "./canvas_movie_controller.js"
import { unzip, setOptions } from './unzipit.module.js';

const DEFAULT_MARKERS = [{'x':50,'y':50,'label':'Apex'},
                         {'x':50,'y':100,'label':'Ruler 0mm'},
                         {'x':50,'y':150,'label':'Ruler 10mm'}
                        ];

// NOTE ./static is needed below but not above!
setOptions({
  workerURL: './static/unzipit-worker.module.js',
  numWorkers: 2,
});

const DISABLED='disabled';

function dict_to_array( dict ) {
    let array = [];
    for (const key in dict) {
        array[parseInt(key)] = dict[key];
    }
    return array;
}

function get_ruler_size(str) {
    const match = str.match(/^Ruler\s*(\d+)mm$/);
    return match ? parseInt(match[1], 10) : null;
}

class TracerController extends MovieController {
    constructor( div_selector, movie_metadata, api_key) {
        super( div_selector );
        this.tracking = false;  // are we tracking a movie?
        this.movie_metadata = movie_metadata;
        this.api_key = api_key;
        this.movie_id = movie_metadata.movie_id;

        // set up the download form & button
        this.download_form = $("#download_form");
        this.download_form.attr('action',`${API_BASE}api/get-movie-trackpoints`);
        this.dl_api_key = $("#dl_api_key");
        this.dl_api_key.attr("value", api_key);
        this.dl_movie_id = $("#dl_movie_id");
        this.dl_movie_id.attr("value", this.movie_id);
        this.download_button = $("#download_button");
        this.download_button.hide(); // Hide the download link until we track or retrack

        // Size the canvas and video player
        $(this.div_selector + " canvas").attr('width',this.movie_metadata.width);
        $(this.div_selector + " canvas").attr('height',this.movie_metadata.height);
        $(this.div_selector + " video").attr('width',this.movie_metadata.width);
        $(this.div_selector + " video").attr('height',this.movie_metadata.height);

        // marker_name_input is the text field for the marker name
        this.marker_name_input = $(this.div_selector + " .marker_name_input");
        this.marker_name_input.on('input',   (_) => { this.marker_name_changed();});
        this.marker_name_input.on('keydown', (e) => { if (e.keyCode==13) this.add_marker_onclick_handler(event);});
        this.add_marker_status = $(this.div_selector + ' .add_marker_status');

        // We need to be able to enable or display the add_marker button, so we record it
        this.add_marker_button = $(this.div_selector + " input.add_marker_button");
        this.add_marker_button.on('click', (event) => { this.add_marker_onclick_handler(event);});

        // Set up the track button
        this.track_button = $(this.div_selector + " input.track_button");
        this.track_button.on('click', () => {this.track_to_end();});

        $(this.div_selector + " span.total-frames-span").text(this.total_frames);

        this.rotate_button = $(this.div_selector + " input.rotate_movie");
        this.rotate_button.prop('disabled',false);
        this.rotate_button.on('click', (_event) => {this.rotate_button_pressed();});

        if (this.last_tracked_frame > 0 ){
            this.track_button.val( RETRACK_MOVIE );
            this.download_button.show();
        }
        this.tracking_status = $(this.div_selector + ' span.add_marker_status');
    }


    // on each change of input, validate the marker name
    marker_name_changed ( ) {
        const val = this.marker_name_input.val();
        // First see if marker name is too short
        if (val.length < MIN_MARKER_NAME_LEN) {
            this.add_marker_status.text("Marker name must be at least "+MIN_MARKER_NAME_LEN+" letters long");
            this.add_marker_button.prop('disabled',true);
            return;
        } else {
            this.add_marker_status.text("");
            this.add_marker_button.prop('disabled',false);
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

    // new marker added
    add_marker_onclick_handler(_e) {
        if (this.marker_name_input.val().length >= MIN_MARKER_NAME_LEN) {
            this.add_marker( 50, 50, this.marker_name_input.val());
            this.marker_name_input.val("");
        }
    }

    // add a tracking circle with the next color
    add_marker(x, y, name) {
        let color = PLANT_MARKER_COLOR;
        this.objects.push( new Marker(x, y, MARKER_RADIUS, color, color, name));
        this.create_marker_table(); // redraw table
        // Finally enable the track-to-end button
        this.track_button.prop('disabled',false);
    }

    // TODO: refactor to eliminate redundancy this.graphdata.calc_scale()
    calculate_scale(markers) {
        let scale = 1, pos_units = "pixels";
        const ruler_markers = markers
            .map(marker => ({ label: marker.name, number: get_ruler_size(marker.name), x: marker.x, y: marker.y }))
            .filter(x => x.number !== null)
            .sort((a, b) => a.number - b.number);

        if (ruler_markers.length >= 2) {
            const ruler_start = ruler_markers[0];
            const ruler_end = ruler_markers[ruler_markers.length - 1];
            const x_ruler_start = ruler_start.x;
            const y_ruler_start = ruler_start.y;
            const x_ruler_end = ruler_end.x;
            const y_ruler_end = ruler_end.y;
            const pixel_distance = Math.sqrt(Math.pow(x_ruler_end - x_ruler_start, 2) + Math.pow(y_ruler_end - y_ruler_start, 2));
            const real_distance = ruler_end.number - ruler_start.number;
            scale = real_distance / pixel_distance;
            pos_units = "mm";
        } else {
            console.log('calculate_scale: Two ruler markers not found. The distance will be in pixels.');
            scale = 1;
            pos_units = "pixels";
        }
        return { scale: scale, pos_units: pos_units };
    }

    create_marker_table() {
        // Generate the HTML for the table body
        let rows = '';
        let calculations = this.calculate_scale(this.objects)
        for (let i=0;i<this.objects.length;i++){
            const obj = this.objects[i];
            if (obj.constructor.name == Marker.name){
                obj.table_cell_id = "td-" + (++cell_id_counter);
                if (calculations.pos_units == 'mm') {
                    obj.loc_mm = "("+ Math.round(obj.x * calculations.scale) + ", " + Math.round(obj.y * calculations.scale) + ")";
                } else {
                    obj.loc_mm = "n/a";
                }
                rows += `<tr>` +
                    `<td class="dot" style="color:${obj.fill};">●</td>` +
                    `<td>${obj.name}</td>` +
                    `<td id="${obj.table_cell_id}">${obj.loc()}</td>` +
                    `<td>${obj.loc_mm}</td><td class="del-row nodemo" object_index="${i}" >🚫</td></tr>`;
            }
        }
        // put the HTML in the window and wire up the delete object method
        $(this.div_selector + " tbody.marker_table_body").html( rows );
        $(this.div_selector + " .del-row").on('click',
                     (event) => {this.del_row(event.target.getAttribute('object_index'));});
        $(this.div_selector + " .del-row").css('cursor','default');
        this.redraw();          // redraw with the markers
        if (demo_mode) {        // be sure to hide the just-added delete option
            $('.nodemo').hide();
        }
    }

    // Delete a row and update the server
    del_row(i) {
        this.objects.splice(i,1);
        this.create_marker_table();
        this.put_markers();
    }

    // Subclassed methods
    // Update the matrix location of the object the moved
    object_did_move(obj) {
        $( "#"+obj.table_cell_id ).text( obj.loc() );
        if (this.frame_number==0 || this.frame_number < this.movie_metadata.total_frames) {
            this.track_button.prop('disabled',false); // enable the button if track point is moved
        }
    }

    // Movement finished; upload new annotations
    object_move_finished(_obj) {
        this.put_markers();
    }

    // Return an array of markers (which are called markers elsewhere...)
    get_markers() {
        let markers = [];
        for (let i=0;i<this.objects.length;i++){
            const obj = this.objects[i];
            if (obj.constructor.name == Marker.name){
                markers.push( {x:obj.x, y:obj.y, label:obj.name} );
            }
        }
        return markers;
    }

    json_markers() {
        return JSON.stringify(this.get_markers());
    }

    // Send the list of current markers to the server.
    // In demo mode, just print a message.
    put_markers() {
        if (demo_mode) {
            $('#demo-popup').fadeIn(300);
            return;
        }
        const put_frame_markers_params = {
            api_key      : this.api_key,
            movie_id     : this.movie_id,
            frame_number : this.frame_number,
            trackpoints  : this.json_markers()
        };
        $.post(`${API_BASE}api/put-frame-trackpoints`, put_frame_markers_params )
            .done( (data) => {
                if (data.error) {
                    alert("Error saving annotations: "+data.message);
                }
            })
            .fail( (res) => {
                console.log("error:",res);
                alert("error from put-frame-trackpoints:\n"+res.responseText);
            });
    }

    /* track_to_end() is called when the track_button ('track to end') button is clicked.
     * It calls the api/track-movie-quque on the server, queuing movie tracking (which takes a while).
     * Here are some pages for notes about playing the video:
     * https://www.w3schools.com/html/tryit.asp?filename=tryhtml5_video_js_prop
     * https://developer.mozilla.org/en-US/docs/Web/HTML/Element/video
     * https://developer.mozilla.org/en-US/docs/Web/Media/Audio_and_video_delivery/Video_player_styling_basics
     * https://blog.logrocket.com/creating-customizing-html5-video-player-css/
     * https://freshman.tech/custom-html5-video/
     * https://medium.com/@nathan5x/event-lifecycle-of-html-video-element-part-1-f63373c981d3
     */
    track_to_end() {
        // Ask the server to track from this frame to the end of the movie.
        // If successfull, set up a status worker to poll
        this.tracking_status.text("Asking server to track movie...");
        this.track_button.prop('disabled',true); // disable it until tracking is finished

        const params = {
            api_key: this.api_key,
            movie_id: this.movie_id,
            frame_start: this.frame_number };

        // post is non-blocking, but running locally on bottle the tracking happens
        // before the post returns.
        this.tracking = true;   // we are tracking
        this.poll_for_track_end();
        this.set_movie_control_buttons();
        $.post(`${API_BASE}api/track-movie-queue`, params ).done( (data) => {
            if(data.error){
                alert(data.message);
                this.track_button.prop('disabled',false); // re-enable
                this.tracking=false;
                this.set_movie_control_buttons();
            } else {
                console.log("no error");
            }
        });
    }

    add_frame_objects( frame ){
        // call back from canvas_movie_controller to add additional objects for 'frame' beyond base image.
        // Add the lines for every previous frame if each previous frame has markers
        if (frame>0 && this.frames[frame-1].markers && this.frames[frame].markers){
            for (let f0=0;f0<frame;f0++){
                var starts = [];
                var ends   = {};
                for (let tp of this.frames[f0].markers){
                    starts.push(tp);
                }
                for (let tp of this.frames[f0+1].markers){
                    ends[tp.label] = tp
                }
                // now add the lines between the markers in the previous frames
                // We could cache this moving from frame to frame, rather than deleting and re-drawing them each time
                for (let st of starts){
                    if (ends[st.label]){
                        this.add_object( new Line(st.x, st.y, ends[st.label].x, ends[st.label].y, 2, "red"));
                    }
                }
            }
        }

        // Add the markers for this frame if this frame has markers
        if (this.frames[frame].markers) {
            for (let tp of this.frames[frame].markers) {
                this.add_object( new Marker(tp.x, tp.y, 10, 'red', 'red', tp.label ));
            }
        }
        this.create_marker_table();
    }

    set_movie_control_buttons()  {
        /* override to disable everything if we are tracking */
        if (this.tracking) {
            $(this.div_controller + ' input').prop('disabled',true); // disable all the inputs
            this.rotate_button.prop('disabled',true);
            return;
        }
        this.rotate_button.prop('disabled',false);
        super.set_movie_control_buttons(); // otherwise run the super class
    }

    /*
     * Poll the server to see if tracking has ended.
     */
    poll_for_track_end() {
        const params = {
            api_key:this.api_key,
            movie_id:this.movie_id,
            get_all_if_tracking_completed: true
        };
        $.post(`${API_BASE}api/get-movie-metadata`, params).done( (data) => {
            if (data.error==false){
                // Send the status back to the UX
                if (data.metadata.status==TRACKING_COMPLETED_FLAG) {
                    if (this.tracking) {
                        this.movie_tracked(data);
                    }
                } else {
                    /* Update the status and track again in 250 msec */
                    this.tracking_status.text(data.metadata.status);
                    this.timeout = setTimeout( ()=>{this.poll_for_track_end();}, TRACKING_POLL_MSEC );
                }
            }
        });
    }

    /** movie is tracked - display the results */
    movie_tracked(data) {

        // This should work. but it is not. So just force a reload until I can figure out what's wrong.
        location.reload(true);

        /***

        this.tracking = false;
        this.tracking_status.text('Movie tracking complete.');
        console.log("before load_movie. this.frames=",this.frames);
        this.load_movie( dict_to_array(data.frames)); // reload the movie
        console.log("after load_movie. this.frames=",this.frames);
        this.download_button.show();
        // change from 'track movie' to 'Retrack movie' and re-enable it
        $(this.div_selector + ' input.track_button').val( RETRACK_MOVIE );
        this.track_button.prop('disabled',false);
        // We do not need to redraw, because the frame hasn't changed
        */
    }

    rotate_button_pressed() {
        // Rotate button pressed. Rotate the  movie and then reload the page and clear the cache
        this.rotate_button.prop('disabled',true);
        $('#firsth2').html(`Asking server to rotate movie 90º counter-clockwise. Please stand by...`);
        const params = {
            api_key: this.api_key,
            movie_id: this.movie_id,
            action: 'rotate90cw'};
        $.post(`${API_BASE}api/edit-movie`, params ).done( (data) => {
            if(data.error){
                alert(data.message);
            } else {
                location.reload(true);
            }
        });
        location.reload(true);
    }

}


// Called when we want to trace a movie for which we do not have frame-by-frame metadata.
// set up the default
var cc;
function trace_movie_one_frame(movie_id, div_controller, movie_metadata, frame0_url, api_key) {
    cc = new TracerController(div_controller, movie_metadata, api_key);
    cc.did_onload_callback = (_) => {
        if (demo_mode) {
            $('#firsth2').html('Movie cannot be traced in demo mode.');
        } else {
            $('#firsth2').html('Movie ready for initial tracing.');
        }
    };

    var frames = [{'frame_url': frame0_url,
                   'markers':DEFAULT_MARKERS }];
    cc.load_movie(frames);
    cc.create_marker_table();
    cc.track_button.prop('disabled',true); // disable it until we have a marker added.
}

// Called when we trace a movie for which we have the frame-by-frame analysis.
async function trace_movie_frames(div_controller, movie_metadata, movie_zipfile, metadata_frames,
                                  api_key,
                                  show_results=true) {
    const movie_frames = [];
    const {entries} = await unzip(movie_zipfile);
    const names = Object.keys(entries).filter(name => name.endsWith('.jpg'));
    const blobs = await Promise.all(names.map(name => entries[name].blob()));
    names.forEach((name, i) => {
        movie_frames[i] = {'frame_url':URL.createObjectURL(blobs[i]),
                     'markers':metadata_frames[i].markers };
    });

    cc = new TracerController(div_controller, movie_metadata, api_key);
    cc.set_movie_control_buttons();
    cc.load_movie(movie_frames);
    cc.track_button.prop('disabled',false); // We have markers, so allow tracking from beginning.
    if (movie_frames.length > 0 ){
        cc.track_button.val( RETRACK_MOVIE );
        cc.download_button.show();
    }
    if (show_results) {
        $('#analysis-results').show();
        graph_data(cc, movie_frames);
    }
}

function graph_data(cc, frames) {
    const frame_labels = [];
    const x_values_mm = [];
    const y_values_mm = [];
    const x_apex_0 = frames[0].markers.find(marker => marker.label === 'Apex').x;
    const y_apex_0 = frames[0].markers.find(marker => marker.label === 'Apex').y;
    let pos_units = "pixels";
    let time_units = "frames";

    if (cc.fpm != null) {
        time_units = "minutes";
    }

    frames.forEach((frame) => {
        const apexMarker = frame.markers.find(marker => marker.label === 'Apex');
        const calculations = calc_scale(frame.markers);
        const scale = calculations.scale;
        pos_units = calculations.pos_units; // TODO - if units change, revert to pixels.

        // If 'Apex' marker is found, push the frame number and the x, y positions
        if (apexMarker) {
            frame_labels.push(cc.fpm ? (Math.floor(1 / cc.fpm) * apexMarker.frame_number) : apexMarker.frame_number); // frame rate = 1 frame/min
            x_values_mm.push((apexMarker.x - x_apex_0) * scale);
            y_values_mm.push((apexMarker.y - y_apex_0) * scale);
        }
    });

    const ctxX = document.getElementById('apex-xChart').getContext('2d');
    const ctxY = document.getElementById('apex-yChart').getContext('2d');

    // Graph for Frame Number or Time vs X Position
    const xChart = new Chart(ctxX, {
        type: 'line',
        data: {
            labels: frame_labels,
            datasets: [
                {
                    label: 'Time vs X Position',
                    data: x_values_mm,
                    borderColor: 'rgba(255, 0, 0, 1)',
                    fill: false,
                    pointRadius: 0
                }
            ]
        },
        options: {
            responsive: false, // Disable Chart.js responsiveness and respect HTML canvas size
            maintainAspectRatio: false,
            scales: {
                x: {
                    title: {
                        display: true,
                        text: 'Time (' + time_units + ')'
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: 'X Position (' + pos_units + ')'
                    }
                }
            },
            plugins: {
                legend: {
                        display: true,
                    labels: {
                        usePointStyle: true,  // Use line instead of a box in the legend
                        boxWidth: 4,         // Make the line shorter in the legend
                        pointStyle: 'line',  // Show a line instead of the default box
                        borderColor: 'rgba(255, 0, 0, 1)'
                    }
                }
            }
        }
    });

    // Graph for Y Position
    const yChart = new Chart(ctxY, {
        type: 'line',
        data: {
            labels: frame_labels,
            datasets: [
                {
                    label: 'Time vs Y Position',
                    data: y_values_mm,
                    borderColor: 'rgba(255, 0, 0, 1)',
                    fill: false,
                    pointRadius: 0
                }
            ]
        },
        options: {
            responsive: false, // Disable Chart.js responsiveness and respect HTML canvas size
            maintainAspectRatio: false,
            scales: {
                x: {
                    title: {
                        display: true,
                        text: 'Time (' + time_units + ')'
                    }
                },
                y: {
                    reverse: true, // flips the pixel y value to bottom left
                    title: {
                        display: true,
                        text: 'Y Position (' + pos_units + ')'
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        usePointStyle: true,  // Use line instead of a box in the legend
                        boxWidth: 4,         // Make the line shorter in the legend
                        pointStyle: 'line',  // Show a line instead of the default box
                        borderColor: 'rgba(255, 0, 0, 1)'
                    }
                }
            }
        }
    });

    function calc_scale(markers) {
        let scale = 1, pos_units = "pixels";
        const ruler_markers = markers
            .map(marker => ({ label: marker.label, number: get_ruler_size(marker.label) }))
            .filter(x => x.number !== null)
            .sort((a, b) => a.number - b.number);

        if (ruler_markers.length >= 2) {
            const extract_ruler_start = ruler_markers[0];
            const extract_ruler_end = ruler_markers[ruler_markers.length - 1];
            const ruler_start = markers.find(marker => marker.label === extract_ruler_start.label);
            const ruler_end = markers.find(marker => marker.label === extract_ruler_end.label);
            const x_ruler_start = ruler_start.x;
            const y_ruler_start = ruler_start.y;
            const x_ruler_end = ruler_end.x;
            const y_ruler_end = ruler_end.y;
            const pixel_distance = Math.sqrt(Math.pow(x_ruler_end - x_ruler_start, 2) + Math.pow(y_ruler_end - y_ruler_start, 2));
            const real_distance = extract_ruler_end.number - extract_ruler_start.number;
            scale = real_distance / pixel_distance;
            pos_units = "mm";
        } else {
            console.log('Two RulerXXmm markers not found. The distance will be in pixels.');
            scale = 1;
            pos_units = "pixels";
        }
        return { scale: scale, pos_units: pos_units };
    }
}

/* Main function called when HTML page loads.
 * Gets metadata for the movie and all traced frames
 */
function trace_movie(div_controller, movie_id, api_key) {

    // Wire up the close button on the demo pop-up
    $('#demo-popup-close').on('click',function() {
        $('#demo-popup').fadeOut(300);
    });

    const params = {
        api_key: api_key,
        movie_id: movie_id,
        frame_start: 0,
        frame_count: MAX_FRAMES
    };
    $.post(`${API_BASE}api/get-movie-metadata`, params ).done( (resp) => {
        console.log("get-movie-metadata=",resp)
        if (resp.error==true) {
            alert(resp.message);
            return;
        }
        const width = resp.metadata.width;
        const height = resp.metadata.height;
        $(div_controller + ' canvas').prop('width',width).prop('height',height);
        if (!resp.metadata.movie_zipfile_url) {
            const frame0 = `${API_BASE}api/get-frame?api_key=${api_key}&movie_id=${movie_id}&frame_number=0&format=jpeg`;
            trace_movie_one_frame(movie_id, div_controller, resp.metadata, frame0);
            return;
        }
        if (demo_mode) {
            $('#firsth2').html(`Movie is traced!</a>`);
        } else {
            $('#firsth2').html(`Movie is traced! Check for errors and retrace as necessary.</a>`);
        }
        trace_movie_frames(div_controller, resp.metadata, resp.metadata.movie_zipfile_url, resp.frames, api_key);
    });
}

export { TracerController, trace_movie, trace_movie_one_frame, trace_movie_frames };
