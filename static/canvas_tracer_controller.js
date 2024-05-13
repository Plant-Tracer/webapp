"use strict";
// code for /analyze
/* jshint esversion: 8 */
/*global api_key */
/*global movie_id */
/*global $ */

/*
 * Tracer Controller:
 * Manages the trackpoints table and retracks the movie as requested by the user.
 */

const MARKER_RADIUS = 10;           // default radius of the marker
const RULER_MARKER_COLOR = 'orange';
const PLANT_MARKER_COLOR = 'red';
const MIN_MARKER_NAME_LEN = 4;  // markers must be this long (allows 'apex')
const ENGINE = 'CV2';
const ENGINE_VERSION = '1.0';
const TRACKING_COMPLETED_FLAG='TRACKING COMPLETED';
const ADD_MARKER_STATUS_TEXT="Drag each marker to the appropriate place on the image. You can also create additional markers."

var cell_id_counter = 0;
var div_id_counter  = 0;
var div_template = '';          // will be set with the div template

import { CanvasController, CanvasItem, Marker, WebImage } from "./canvas_controller.js";
import { MovieController } from "./canvas_movie_controller.js"


class TracerController extends MovieController {
    constructor( div_selector, movie_metadata, api_key) {
        super( div_selector );
        this.div_selector = div_selector;
        this.tracking = false;  // are we tracking a movie?
        this.movie_metadata = movie_metadata;
        const movie_id = movie_metadata.movie_id;

        // set up the download button
        this.download_link = $(div_selector + " input.download_button");
        this.download_link.attr('href',`/api/get-movie-trackpoints?api_key=${api_key}&movie_id=${movie_id}`);
        this.download_link.hide();

        // Size the canvas and video player
        $(div_selector + " canvas").attr('width',this.movie_metadata.width);
        $(div_selector + " canvas").attr('height',this.movie_metadata.height);
        $(div_selector + " video").attr('width',this.movie_metadata.width);
        $(div_selector + " video").attr('height',this.movie_metadata.height);

        // Hide the download link until we track or retrack

        // marker_name_input is the text field for the marker name
        this.marker_name_input = $(div_selector + "input.marker_name_input");
        this.marker_name_input.on('input',   (event) => { this.marker_name_changed(event);});
        this.marker_name_input.on('keydown', (event) => { if (event.keyCode==13) this.add_marker_onclick_handler(event);});

        // We need to be able to enable or display the add_marker button, so we record it
        this.add_marker_button = $(div_selector + " input.add_marker_button");
        this.add_marker_button.on('click', (event) => { this.add_marker_onclick_handler(event);});

        // We need to be able to enable or display the
        this.track_button = $(div_selector + " input.track_button");
        this.track_button.on('click', (event) => {this.track_to_end(event);});
        this.track_button.prop('disabled',true); // disable it until we have a marker added.

        $(div_selector + " span.total-frames-span").text(this.total_frames);

        this.rotate_button = $(div_selector + " input.rotate_button");
        this.rotate_button.prop('diabled',false);
        this.rotate_button.on('click', (_event) => {this.rotate_button_pressed();});

        this.track_button = $(div_selector + " input.track_button");
        if (this.last_tracked_frame > 0 ){
            this.track_button.val( 'retrack movie' );
            this.download_link.show();
        }
    }


    // on each change of input, validate the marker name
    marker_name_changed (_) {
        const val = this.marker_name_input.val();
        // First see if marker name is too short
        if (val.length < MIN_MARKER_NAME_LEN) {
            this.add_marker_status.text("Marker name must be at least "+MIN_MARKER_NAME_LEN+" letters long");
            this.add_marker_button.prop('disabled',true);
            return;
        } else {
            this.add_marker_status.text("");
            this.add_marker_button.prop('enabled',true);
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

    create_marker_table() {
        // Generate the HTML for the table body
        let rows = '';
        for (let i=0;i<this.objects.length;i++){
            let obj = this.objects[i];
            if (obj.constructor.name == Marker.name){
                obj.table_cell_id = "td-" + (++cell_id_counter);
                rows += `<tr>` +
                    `<td class="dot" style="color:${obj.fill};">●</td>` +
                    `<td>${obj.name}</td>` +
                    `<td id="${obj.table_cell_id}">${obj.loc()}</td><td>n/a</td><td class="del-row" object_index="${i}" >🚫</td></tr>`;
            }
        }
        $(this.div_selector + " tbody.marker_table_body").html( rows );
        this.redraw();          // redraw with the markers

        // wire up the delete object method
        $(this.div_selector + " .del-row").on('click', (event) => {this.del_row(event.target.getAttribute('object_index'));});
        $(this.div_selector + " .del-row").css('cursor','default');
    }

    // Delete a row and update the server
    del_row(i) {
        this.objects.splice(i,1);
        this.create_marker_table();
        this.put_trackpoints();
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
        this.put_trackpoints();
    }

    // Return an array of trackpoints
    get_trackpoints() {
        let trackpoints = [];
        for (let i=0;i<this.objects.length;i++){
            let obj = this.objects[i];
            if (obj.constructor.name == Marker.name){
                trackpoints.push( {x:obj.x, y:obj.y, label:obj.name} );
            }
        }
        return trackpoints;
    }

    json_trackpoints() {
        return JSON.stringify(this.get_trackpoints());
    }

    put_trackpoints() {
        // If we are putting the frame, we already have the frame_id
        let put_frame_analysis_params = {
            api_key      : api_key,
            movie_id     : this.movie_id,
            frame_number : this.frame_number,
            trackpoints  : this.json_trackpoints()
        };
        $.post('/api/put-frame-analysis', put_frame_analysis_params ).done( (data) => {
            if (data.error) {
                alert("Error saving annotations: "+data.message);
            }
        });
    }

    /* track_to_end() is called when the track_button ('track to end') button is clicked.
     * It calls the /api/track-movie-quque on the server, queuing movie tracking (which takes a while).
     * Here are some pages for notes about playing the video:
     * https://www.w3schools.com/html/tryit.asp?filename=tryhtml5_video_js_prop
     * https://developer.mozilla.org/en-US/docs/Web/HTML/Element/video
     * https://developer.mozilla.org/en-US/docs/Web/Media/Audio_and_video_delivery/Video_player_styling_basics
     * https://blog.logrocket.com/creating-customizing-html5-video-player-css/
     * https://freshman.tech/custom-html5-video/
     * https://medium.com/@nathan5x/event-lifecycle-of-html-video-element-part-1-f63373c981d3
     */
    track_to_end(_) {
        // Ask the server to track from this frame to the end of the movie.
        // If successfull, set up a status worker to poll
        this.tracking_status.text("Asking server to track movie...");
        this.track_button.prop('disabled',true); // disable it until tracking is finished
        const formData = new FormData();
        formData.append('api_key',api_key);
        formData.append('movie_id',this.movie_id);
        formData.append('frame_start',this.frame_number);
        formData.append('engine_name',ENGINE);
        formData.append('engine_version',ENGINE_VERSION);
        fetch('/api/track-movie-queue', {
            method:'POST',
            body: formData })
            .then((response) => response.json())
            .then((data) => {
                if(data.error){
                    alert(data.message);
                } else {
                    this.tracking = true;   // we are tracking
                    this.set_movie_control_buttons();
                    this.tracking_status.text(data.message);
                    this.poll_for_track_end();
                }
            });
    }

    add_frame_objects( frame ){
        // called back canvie_movie_controller to add additional objects for 'frame' beyond base image.
        // Add the lines for every previous frame if each previous frame has trackpoints
        if (frame>0 && this.frames[frame-1].trackpoints && this.frame[frame] && trackpoints){
            var starts = [];
            var ends   = [];
            for (let tp of this.frames[frame-1].trackpoints){
                starts[tp.label] = tp
            }
            for (let tp of this.frames[frame-1].trackpoints){
                ends[tp.label].end = tp
            }
            // now add the lines between the trackpoints in the previous frames
            // We could cache this moving from frame to frame, rather than deleting and re-drawing them each time
            for (let st of starts){
                if (ends[st.label]){
                    this.add_object( Line(st.x, st.y, ends[st.label].x, ends[st.label].y, 2, "red"));
                }
            }
        }

        // Add the trackpoints for this frame if this frame has trackpoints
        if (this.frames[frame].trackpoints) {
            for (let tp of this.frames[frame].trackpoints) {
                this.add_object( Marker(tp.x, tp.y, 10, 'red', 'red', tp.label ));
            }
        }
    }

    set_movie_control_buttons()  {
        /* override to disable everything if we are tracking */
        if (this.tracking) {
            $(this.div_controller + ' input').prop('disabled',true); // disable all the inputs
            return;
        }
        super.set_movie_control_buttons(); // otherwise run the super class
    }

    /*
     * Poll the server to see if tracking has ended.
     */
    poll_for_track_end() {
        console.log(Date.now(),"update_tracked_movie_status_from_server obj=",obj);
        const formData = new FormData();
        formData.append('api_key',obj.api_key);
        formData.append('movie_id',obj.movie_id);
        formData.append('get_all_if_tracking_completed',true);
        fetch('/api/get-movie-metadata', {
            method:'POST',
            body: formData })
            .then((response) => response.json())
            .then((data) => {
                console.log(Date.now(),"get-movie-metadata (movie_id=",obj.movie_id,") got = ",
                            data,"metadata:",data.metadata,"status:",data.metadata.status);
                if (data.error==false){
                    // Send the status back to the UX
                    if (data.status==TRACKING_COMPLETED_FLAG) {
                        movie_tracked(data);
                    } else {
                        /* Update the status and track again in 250 msec */
                        this.tracking_status.text(data.metadata.status);
                        this.timeout = setTimeout( ()=>{this.wait_for_track_end();} );
                    }
                }
            });
    }

    /** movie is tracked - display the results */
    movie_tracked(data) {
        console.log("movie_tracked data: ",data);
        this.tracking = false;
        this.tracking_status.text('Movie tracking complete.');
        this.download_link.show();
        // change from 'track movie' to 'retrack movie' and re-enable it
        $(this.div_selector + ' input.track_button').val( 'retrack movie.' );
        this.track_button.prop('disabled',false);
        // We do not need to redraw, because the frame hasn't changed
        self.set_movie_control_buttons();
    }

    async rotate_button_pressed() {
        // Rotate button pressed. Rotate the  movie and then reload the page and clear the cache
        let formData = new FormData();
        formData.append("api_key",  api_key);   // on the upload form
        formData.append('movie_id', this.movie_id);
        formData.append('action', 'rotate90cw');
        const r = await fetch('/api/edit-movie', { method:"POST", body:formData});
        console.log("r=",r);
        if (!r.ok) {
            console.log('could not rotate. r=',r);
            return;
        }
        location.reload(true);
    }
}

// Called when the page is loaded
function trace_movie(api_key, movie_id) {
    // Get the metadata
    // Say which movie we are working on
    const formData = new FormData();
    formData.append('api_key',api_key);
    formData.append('movie_id',movie_id);
    fetch('/api/get-movie-metadata', {
        method:'POST',
        body: formData})
        .then((response) => response.json())
        .then((data) => {
            if (data.error==true) {
                $('#firsth2').html(`Movie #${movie_id}: Cannot load metadata: ${data.message}`);
                return;
            }
            $('#firsth2').html(`Movie #${movie_id}: ready to trace`);
            const cc = new TracerController( div_id, movie_id, data );
        });
}

export { TracerController };

// Call analyze_move on load
//$( document ).ready( function() {
//    trace_movie( api_key, movie_id);
//});
