"use strict";

//code for /analyze

/* eslint-env es6 */
/* global LAMBDA_API_BASE */

/* jshint esversion: 8 */

/*
 * Tracer Controller:
 * Manages the table of markers and tracing the movie as requested by the user.
 *
 */

const MARKER_RADIUS = 10;           // default radius of the marker
const PLANT_MARKER_COLOR = 'red';
const MIN_MARKER_NAME_LEN = 4;  // markers must be this long (allows 'apex')
const TRACKING_COMPLETED_FLAG='TRACKING COMPLETED';
const TRACKING_POLL_MSEC=1000;
const TRACE_MOVIE = 'Trace movie';
const RETRACE_MOVIE = 'Retrace movie';
const MAX_FRAMES = 1000000;

var cell_id_counter = 0;

import { $ } from "./utils.js";
import { Marker,Line } from "./canvas_controller.mjs";
import { MovieController } from "./canvas_movie_controller.js"
import { unzip, setOptions } from './unzipit.module.mjs';

// The default markers get added to a movie that is not tracked.
// Note that a movie that is just tracked at frame 0 is tracked...
const DEFAULT_MARKERS = [{'x':50,'y':50,'label':'Apex'},
                         {'x':50,'y':100,'label':'Ruler 0mm'},
                         {'x':50,'y':150,'label':'Ruler 10mm'}
                        ];

// NOTE ./static is needed below but not above!
setOptions({
  workerURL: './static/unzipit-worker.module.mjs',
  numWorkers: 2,
});

const DISABLED='disabled';


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
        // Last frame index that has trackpoints (from API). -1 = none traced yet; only frame 0 viewable.
        this.last_tracked_frame = (movie_metadata.last_frame_tracked != null && movie_metadata.last_frame_tracked !== undefined)
            ? movie_metadata.last_frame_tracked : -1;
        this.total_frames = (movie_metadata.total_frames != null && movie_metadata.total_frames !== undefined)
            ? movie_metadata.total_frames : 0;

        // set up the download form & button
        this.download_form = $("#download_form");
        this.download_form.attr('action',`${API_BASE}api/get-movie-trackpoints`);
        this.dl_api_key = $("#dl_api_key");
        this.dl_api_key.attr("value", api_key);
        this.dl_movie_id = $("#dl_movie_id");
        this.dl_movie_id.attr("value", this.movie_id);
        this.download_button = $("#download_button");
        this.download_button.hide(); // Hide the download link until we track or retrack

        // Size the canvas and video from metadata when present; else leave default until first frame loads.
        const w = this.movie_metadata.width;
        const h = this.movie_metadata.height;
        if (w != null && h != null && w > 0 && h > 0) {
            $(this.div_selector + " canvas").attr('width', w).attr('height', h);
            $(this.div_selector + " video").attr('width', w).attr('height', h);
        }

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
        this.rotate_button.hide();
        this.rotate_button.prop(DISABLED, true);
        this.rotate_button.on('click', (_event) => {this.rotate_button_pressed();});

        // Only show "Retrace" and download when the movie has been fully traced (last_frame_tracked set and at end).
        const fullyTraced = this.total_frames > 0 && this.last_tracked_frame >= 0 &&
            this.last_tracked_frame >= this.total_frames - 1;
        if (fullyTraced) {
            this.track_button.val(RETRACE_MOVIE);
            this.download_button.show();
        }
        this.tracking_status = $(this.div_selector + ' span.add_marker_status');

        // Remember zoom per movie (movie_id is a GUID); restore from localStorage on load, save on change.
        this.setup_zoom_storage('analysis_zoom_' + this.movie_id);
    }

    /** If Lambda is configured, call Flask API at API_BASE api/track/lambda-health (which probes Lambda status); else enable Track. */
    async enableTrackButtonIfAllowed() {
        if (typeof LAMBDA_API_BASE === 'undefined' || !LAMBDA_API_BASE) {
            this.track_button.prop(DISABLED, false);
            return;
        }
        try {
            const r = await fetch(`${API_BASE}api/track/lambda-health`, { method: 'GET' });
            const data = r.ok ? await r.json() : {};
            if (data.status === 'ok') {
                this.track_button.prop(DISABLED, false);
                this.tracking_status.text('');
            } else {
                this.tracking_status.text('Tracking unavailable (Lambda not reachable).');
                this.track_button.prop(DISABLED, true);
            }
        } catch (_e) {
            this.tracking_status.text('Tracking unavailable (Lambda not reachable).');
            this.track_button.prop(DISABLED, true);
        }
    }


    // on each change of input, validate the marker name
    marker_name_changed ( ) {
        const val = this.marker_name_input.val();
        // First see if marker name is too short
        if (val.length < MIN_MARKER_NAME_LEN) {
            this.add_marker_status.text("Marker name must be at least "+MIN_MARKER_NAME_LEN+" letters long");
            this.add_marker_button.prop(DISABLED,true);
            return;
        } else {
            this.add_marker_status.text("");
            this.add_marker_button.prop(DISABLED,false);
        }
        // Make sure it isn't in use
        for (let i=0;i<this.objects.length; i++){
            if(this.objects[i].name == val){
                this.add_marker_status.text("That name is in use, choose another.");
                this.add_marker_button.prop(DISABLED,true);
                return;
            }
        }
        this.add_marker_status.text('');
        this.add_marker_button.prop(DISABLED,false);
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
        this.track_button.prop(DISABLED,false);
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
        if (this.frame_number === 0 || (this.total_frames > 0 && this.frame_number < this.total_frames)) {
            this.enableTrackButtonIfAllowed(); // enable if Lambda (when configured) is reachable
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
            trackpoints  : JSON.stringify(this.get_markers()) // markers as a JSON string because we do POST as a form, not as REST
        };
        for (let tp of this.get_markers()) {
            console.log("frame=",this.frame_number,"tp=",tp);
        }
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
     * Requests tracking via the Lambda API (POST LAMBDA_API_BASE + 'api/v1' with action 'track-movie').
     * Here are some pages for notes about playing the video:
     * https://www.w3schools.com/html/tryit.asp?filename=tryhtml5_video_js_prop
     * https://developer.mozilla.org/en-US/docs/Web/HTML/Element/video
     * https://developer.mozilla.org/en-US/docs/Web/Media/Audio_and_video_delivery/Video_player_styling_basics
     * https://blog.logrocket.com/creating-customizing-html5-video-player-css/
     * https://freshman.tech/custom-html5-video/
     * https://medium.com/@nathan5x/event-lifecycle-of-html-video-element-part-1-f63373c981d3
     */
    track_to_end() {
        // Ask the Lambda API to track from this frame to the end of the movie.
        if (typeof LAMBDA_API_BASE === 'undefined' || !LAMBDA_API_BASE) {
            this.tracking_status.text("Tracking unavailable (Lambda URL not configured).");
            return;
        }
        $('#status-big').html('Movie is being traced...');
        $(this.div_selector).addClass('tracing-dimmed');
        this.tracking_status.text("Asking Lambda to trace movie...");
        this.track_button.prop(DISABLED, true);
        this.tracking = true;
        this.poll_for_track_end();
        this.set_movie_control_buttons();

        const url = LAMBDA_API_BASE.replace(/\/$/, '') + '/api/v1';
        const body = JSON.stringify({
            action: 'track-movie',
            api_key: this.api_key,
            movie_id: this.movie_id,
            frame_start: this.frame_number
        });
        fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: body
        })
            .then((res) => res.json().then((data) => ({ status: res.status, data })).catch(() => ({ status: res.status, data: null })))
            .then(({ status, data }) => {
                if (status !== 200) {
                    const msg = (data && data.message) ? data.message : `Tracking request failed (${status}).`;
                    this.tracking = false;
                    $(this.div_selector).removeClass('tracing-dimmed');
                    this.set_movie_control_buttons();
                    this.enableTrackButtonIfAllowed();
                    this.tracking_status.text(msg);
                    alert(msg);
                    return;
                }
                if (data && data.error) {
                    alert(data.message || 'Tracking failed.');
                    this.tracking = false;
                    $(this.div_selector).removeClass('tracing-dimmed');
                    this.set_movie_control_buttons();
                    this.enableTrackButtonIfAllowed();
                }
            })
            .catch((err) => {
                this.tracking = false;
                $(this.div_selector).removeClass('tracing-dimmed');
                this.set_movie_control_buttons();
                this.enableTrackButtonIfAllowed();
                const msg = err && err.message ? err.message : "Tracking request failed.";
                this.tracking_status.text(msg);
                alert(msg);
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

    /** Highest frame index the user may navigate to (last frame with trackpoints; 0 if none traced yet). */
    getMaxViewableFrame() {
        if (!this.frames || this.frames.length === 0) return 0;
        if (this.last_tracked_frame < 0) return 0;
        return Math.min(this.last_tracked_frame, this.frames.length - 1);
    }

    goto_frame(frame) {
        const maxViewable = this.getMaxViewableFrame();
        frame = parseInt(frame, 10);
        if (!Number.isNaN(frame) && frame > maxViewable) {
            frame = maxViewable;
        }
        super.goto_frame(frame);
    }

    set_movie_control_buttons()  {
        /* override to disable everything if we are tracking */
        if (this.tracking) {
            $(this.div_controller + ' input').prop(DISABLED,true); // disable all the inputs
            this.rotate_button.prop(DISABLED, true);
            return;
        }
        if (this.rotate_button.is(':visible')) {
            this.rotate_button.prop(DISABLED, false);
        }
        this.max_frame_index = this.getMaxViewableFrame();
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

    /** Tracing completed - stop polling, load zip (wait up to 5s if needed), then show full movie. */
    movie_tracked(_data) {
        this.tracking = false;
        this.set_movie_control_buttons();
        this.tracking_status.text('Tracing complete. Loading movie...');

        const self = this;
        const div = (this.div_selector || 'div#tracer').replace(/\s+$/, '');
        const maxZipWaitMs = 5000;
        const zipPollMs = 500;

        /** Resolves with { zipUrl, metadata, frames } when zip is available, or rejects after maxZipWaitMs. */
        function waitForZip() {
            return new Promise((resolve, reject) => {
                if (_data.metadata && _data.metadata.movie_zipfile_url) {
                    resolve({ zipUrl: _data.metadata.movie_zipfile_url, metadata: _data.metadata, frames: _data.frames || {} });
                    return;
                }
                const deadline = Date.now() + maxZipWaitMs;
                function poll() {
                    if (Date.now() > deadline) {
                        reject(new Error('ZIP file did not become available in time. Please refresh and try again.'));
                        return;
                    }
                    self.tracking_status.text('Waiting for ZIP file to be processed...');
                    $.post(`${API_BASE}api/get-movie-metadata`, {
                        api_key: self.api_key,
                        movie_id: self.movie_id,
                        frame_start: 0,
                        frame_count: MAX_FRAMES,
                        get_all_if_tracking_completed: true
                    }).done((resp) => {
                        if (resp.error || !resp.metadata) {
                            setTimeout(poll, zipPollMs);
                            return;
                        }
                        if (resp.metadata.movie_zipfile_url) {
                            resolve({
                                zipUrl: resp.metadata.movie_zipfile_url,
                                metadata: resp.metadata,
                                frames: resp.frames || {}
                            });
                            return;
                        }
                        setTimeout(poll, zipPollMs);
                    }).fail(() => setTimeout(poll, zipPollMs));
                }
                poll();
            });
        }

        waitForZip()
            .then(({ zipUrl, metadata, frames }) => {
                $(div).removeClass('tracing-dimmed');
                const framesToUse = preserve_frame0_markers_from_controller(frames);
                trace_movie_frames(div, metadata, zipUrl, framesToUse, self.api_key, true);
                $(self.div_selector + ' input.track_button').val(RETRACE_MOVIE);
                self.track_button.prop(DISABLED, false);
                self.download_button.show();
                $('#status-big').html('Press play &#9654; to watch the trackpoints.');
            })
            .catch((err) => {
                $(div).removeClass('tracing-dimmed');
                self.tracking_status.text('');
                self.enableTrackButtonIfAllowed();
                alert(err.message || 'Failed to load traced movie.');
            });
    }

    rotate_button_pressed() {
        // Rotate: server clears tracking, updates rotation_steps, triggers Lambda. Reload when done.
        this.rotate_button.prop(DISABLED, true);
        $('#status-big').html(`Asking server to rotate movie 90º clockwise. Please stand by...`);
        const params = {
            api_key: this.api_key,
            movie_id: this.movie_id,
            action: 'rotate90cw'};
        $.post(`${API_BASE}api/edit-movie`, params).done((data) => {
            if (data.error) {
                alert(data.message);
                this.rotate_button.prop(DISABLED, false);
            } else {
                location.reload(true);
            }
        });
    }

}


// Called when we want to trace a movie for which we do not have frame-by-frame metadata.
// set up the default
var cc;                         // where we hold the controller
function trace_movie_one_frame(_movie_id, div_controller, movie_metadata, frame0_url, metadata_frames, api_key) {
    cc = new TracerController(div_controller, movie_metadata, api_key);
    cc.did_onload_callback = (imgStack) => {
        if (imgStack && imgStack.img && (cc.movie_metadata.width == null || cc.movie_metadata.height == null)) {
            const nw = imgStack.img.naturalWidth;
            const nh = imgStack.img.naturalHeight;
            if (nw > 0 && nh > 0) {
                cc.movie_metadata.width = nw;
                cc.movie_metadata.height = nh;
                $(cc.div_selector + ' canvas').attr('width', nw).attr('height', nh);
                $(cc.div_selector + ' video').attr('width', nw).attr('height', nh);
            }
        }
        cc.rotate_button.show();
        cc.rotate_button.prop(DISABLED, false);
        if (demo_mode) {
            $('#status-big').html('Movie cannot be traced in demo mode.');
        } else {
            $('#status-big').html('Movie ready for initial tracing.');
        }
    };

    var frames = [{'frame_url': frame0_url,
                   'markers':DEFAULT_MARKERS }];
    // If we have markers for frame 0, use them instead
    if (metadata_frames && metadata_frames[0] && metadata_frames[0].markers) {
        frames[0].markers = metadata_frames[0].markers;
    }

    cc.load_movie(frames);
    cc.create_marker_table();
    cc.track_button.prop(DISABLED,true); // disable it until we have a marker added.
}

// Called when we trace a movie for which we have the frame-by-frame analysis.
/** Extract frame index from zip entry name (e.g. frame_0000.jpg -> 0) for stable sort. */
function frame_index_from_zip_name(name) {
    const m = name.match(/frame_(\d+)\.jpg$/i);
    return m ? parseInt(m[1], 10) : 0;
}

async function trace_movie_frames(div_controller, movie_metadata, movie_zipfile, metadata_frames,
                                  api_key,
                                  show_results=true) {
    const movie_frames = [];
    const {entries} = await unzip(movie_zipfile);
    const names = Object.keys(entries).filter(name => name.endsWith('.jpg'));
    names.sort((a, b) => frame_index_from_zip_name(a) - frame_index_from_zip_name(b));
    const blobs = await Promise.all(names.map(name => entries[name].blob()));
    names.forEach((_name, i) => {
        // When zip exists but no tracking has been done, metadata_frames may be empty or sparse.
        const frameData = metadata_frames && metadata_frames[i];
        const markers = (frameData && frameData.markers) ? frameData.markers : [...DEFAULT_MARKERS];
        movie_frames[i] = {'frame_url': URL.createObjectURL(blobs[i]), 'markers': markers};
    });

    cc = new TracerController(div_controller, movie_metadata, api_key);
    cc.did_onload_callback = (imgStack) => {
        if (imgStack && imgStack.img && (cc.movie_metadata.width == null || cc.movie_metadata.height == null)) {
            const nw = imgStack.img.naturalWidth;
            const nh = imgStack.img.naturalHeight;
            if (nw > 0 && nh > 0) {
                cc.movie_metadata.width = nw;
                cc.movie_metadata.height = nh;
                $(cc.div_selector + ' canvas').attr('width', nw).attr('height', nh);
                $(cc.div_selector + ' video').attr('width', nw).attr('height', nh);
            }
        }
        cc.rotate_button.show();
        cc.rotate_button.prop(DISABLED, false);
    };
    cc.set_movie_control_buttons();
    cc.load_movie(movie_frames);
    cc.enableTrackButtonIfAllowed(); // enable Track when Lambda (if configured) is reachable
    // Track button label and download visibility are set in constructor from last_tracked_frame / total_frames.
    if (show_results) {
        $('#analysis-results').show();
        graph_data(cc, movie_frames);
    }
}

function graph_data(cc, frames) {
    const frame_labels = [];
    const x_values_mm = [];
    const y_values_mm = [];
    const firstMarkers = (frames[0] && frames[0].markers) || [];
    const apex0 = firstMarkers.find(marker => marker.label === 'Apex');
    const x_apex_0 = (apex0 && apex0.x != null) ? apex0.x : 0;
    const y_apex_0 = (apex0 && apex0.y != null) ? apex0.y : 0;
    let pos_units = "pixels";
    let time_units = "frames";

    if (cc.fpm != null) {
        time_units = "minutes";
    }

    frames.forEach((frame) => {
        const markers = frame.markers || [];
        const apexMarker = markers.find(marker => marker.label === 'Apex');
        const calculations = calc_scale(markers);
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
    const _xChart = new Chart(ctxX, {
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
    const _yChart = new Chart(ctxY, {
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
 * Gets metadata for the movie and traced frames. If no zip yet, shows frame 0 only (no polling).
 * User places markers and clicks "Trace movie"; we then poll only for tracing to complete,
 * then load the zip once (wait up to 5s if needed) and stop polling.
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
        if (width != null && height != null && width > 0 && height > 0) {
            $(div_controller + ' canvas').prop('width', width).prop('height', height);
        }
        if (!resp.metadata.movie_zipfile_url) {
            // No zip yet: show frame 0 only. User places markers and clicks "Trace movie". No polling.
            const frameBase = (typeof LAMBDA_API_BASE !== 'undefined' && LAMBDA_API_BASE) ? LAMBDA_API_BASE : '';
            const frame0 = `${frameBase}api/v1/frame?api_key=${api_key}&movie_id=${movie_id}&frame_number=0&size=analysis`;
            trace_movie_one_frame(movie_id, div_controller, resp.metadata, frame0, resp.frames, api_key);
            if (demo_mode) {
                $('#status-big').html('Movie ready for tracing.');
            } else {
                $('#status-big').html('Place markers and click Trace movie to start tracing.');
            }
            return;
        }
        const showResults = is_movie_tracked(resp.metadata);
        if (demo_mode) {
            $('#status-big').html(showResults ? 'Movie is traced!' : 'Movie ready for tracing.');
        } else {
            $('#status-big').html(showResults ? 'Movie is traced! Check for errors and retrace as necessary.' : 'Movie ready for tracing. Place markers and click Trace movie.');
        }
        trace_movie_frames(div_controller, resp.metadata, resp.metadata.movie_zipfile_url, resp.frames, api_key, showResults);
    });
}

/** If global cc exists from one-frame view, merge its frame 0 markers into frames so they are not lost when zip loads. */
function preserve_frame0_markers_from_controller(frames) {
    if (typeof cc === 'undefined' || !cc.frames || !cc.frames[0] || !cc.frames[0].markers || !cc.frames[0].markers.length) {
        return frames;
    }
    const out = (typeof frames === 'object' && frames !== null && !Array.isArray(frames)) ? { ...frames } : (Array.isArray(frames) ? [...frames] : {});
    const f0 = (out[0] != null) ? { ...out[0] } : {};
    f0.markers = cc.frames[0].markers;
    out[0] = f0;
    return out;
}

/** True only when the movie has been tracked (at least 2 frames with trackpoints or status TRACKING COMPLETED). */
function is_movie_tracked(metadata) {
    if (!metadata) return false;
    if (metadata.status === 'TRACKING COMPLETED') return true;
    const last = metadata.last_frame_tracked;
    const total = metadata.total_frames;
    return (last != null && total != null && total > 1 && last >= 1);
}

export { TracerController, trace_movie, trace_movie_one_frame, trace_movie_frames };
