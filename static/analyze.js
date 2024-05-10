"use strict";
// code for /analyze
/* jshint esversion: 8 */
/*global api_key */
/*global movie_id */

const DEFAULT_R = 10;           // default radius of the marker
const MIN_MARKER_NAME_LEN = 4;  // markers must be this long (allows 'apex')
var cell_id_counter = 0;
var div_id_counter  = 0;
var div_template = '';          // will be set with the div template

const CIRCLE_COLORS = ['#ffe119', '#f58271', '#f363d8', '#918eb4',
                       '#46f0f0', '#f032e6', '#bcf60c', '#fabebe', '#008080', '#e6beff',
                       '#9a6324', '#fffac8', '#800000', '#aaffc3', '#808000', '#ffd8b1',
                       '#000075', '#808080', '#e6194b', ];

const ENGINE = 'CV2';
const ENGINE_VERSION = '1.0';
const TRACKING_COMPLETED_FLAG='TRACKING COMPLETED';
const ADD_MARKER_STATUS_TEXT="Drag each marker to the appropriate place on the image. You can also create additional markers."

class MovieTrackerController extends MovieController {
    constructor( div_selector, zoom_selector
        this.this_id         = this_id;
        this.canvasId        = 0;
        this.movie_id        = movie_id;       // the movie being analyzed
}

        this.last_tracked_frame = movie_metadata.last_tracked_frame;
        this.tracking_status = $(`#${this.this_id} .tracking_status`);
        this.add_marker_status    = $(`#${this_id}      .add_marker_status`);
        this.download_link        = $(`#${this.this_id} .download_link`);
        this.download_button      = $(`#${this.this_id} .download_button`);
        this.tracking = false;  // are we tracking a movie?
        console.log("PlantTracer movie_id=",movie_id,"metadata=",movie_metadata);

        this.download_link.attr('href',`/api/get-movie-trackpoints?api_key=${api_key}&movie_id=${movie_id}`);

        // Size the canvas and video player if we know the sizes
        if (this.movie_metadata.width && this.movie_metadata.height) {
            $(`#${this.this_id} canvas`).attr('width',this.movie_metadata.width);
            $(`#${this.this_id} canvas`).attr('height',this.movie_metadata.height);
            $(`#${this.this_id} video`).attr('width',this.movie_metadata.width);
            $(`#${this.this_id} video`).attr('height',this.movie_metadata.height);
        }

        // Hide the download link until we track or retrack
        this.download_link.hide();

        // marker_name_input is the text field for the marker name
        this.marker_name_input = $(`#${this_id} input.marker_name_input`);
        this.marker_name_input.on('input',   (event) => { this.marker_name_input_handler(event);});
        this.marker_name_input.on('keydown', (event) => { if (event.keyCode==13) this.add_marker_onclick_handler(event);});

        // We need to be able to enable or display the add_marker button, so we record it
        this.add_marker_button = $(`#${this_id} input.add_marker_button`);
        this.add_marker_button.on('click', (event) => { this.add_marker_onclick_handler(event);});

        // We need to be able to enable or display the
        this.track_button = $(`#${this_id} input.track_button`);
        this.track_button.on('click', (event) => {this.track_to_end(event);});
        this.track_button.prop('disabled',true); // disable it until we have a marker added.

        this.download_button = $(`#${this_id} input.download_button`);

        $(`#${this.this_id} span.total-frames-span`).text(this.total_frames);

        this.rotate_button = $(`#${this.this_id} input.rotate_button`);
        this.rotate_button.prop('diabled',false);
        this.rotate_button.on('click', (_event) => {this.rotate_button_pressed();});

        this.track_button = $(`#${this.this_id} input.track_button`);

        if (this.last_tracked_frame > 0 ){
            this.track_button.val( 'retrack movie' );
            this.download_link.show();
        }
    }


    // on each change of input, validate the marker name
    marker_name_input_handler (_e) {
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
        // Find out how many circles there are
        let count = 0;
        for (let i=0;i<this.objects.length;i++){
            if (this.objects[i].constructor.name == Marker.name) count+=1;
        }

        let color = CIRCLE_COLORS[count];
        this.objects.push( new Marker(x, y, DEFAULT_R, color, color, name));
        this.create_marker_table();
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
        $(`#${this.this_id} tbody.marker_table_body`).html( rows );
        this.redraw('add_marker');

        // wire up the delete object method
        $(`#${this.this_id} .del-row`).on('click', (event) => {this.del_row(event.target.getAttribute('object_index'));});
        $(`#${this.this_id} .del-row`).css('cursor','default');
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
    track_to_end(_event) {
        // get the next frame and apply tracking logic
        // First launch the status worker
        /* Disabled because Amazon's back end isn't multi-threaded */
        this.tracking = true;   // we are tracking
        this.set_movie_control_buttons();

        /*
         * redo this so that it uses a timer, not a webworker

        if (window.Worker) {
            this.status_worker = new Worker(STATUS_WORKER);
            this.status_worker.onmessage = (e) => {
                // Got back a message
                console.log("got e.data=",e.data,"status=",e.data.status);
                this.tracking_status.text( e.data.status );
                if (e.data.status==TRACKING_COMPLETED_FLAG) {
                    this.tracking = false; // done tracking
                    this.set_movie_control_buttons();
                    this.movie_tracked();
                    this.total_frames = e.data.total_frames;
                    $(`#${this.this_id} span.total-frames-span`).text(this.total_frames);
                }
            };
            this.status_worker.postMessage( {movie_id:movie_id, api_key:api_key} );
        } else {
            alert("Your browser does not support web workers. You cannot track movies.");
        }
        */

        console.log("track_to_end start");
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
            body: formData
        })
        .then((response) => response.json())
            .then((data) => {
                if(data.error){
                    alert(data.message);
                } else {
                    this.tracking_status.text(data.message);
                }
            });
    }

    /** movie is tracked - display the results */
    movie_tracked() {
        console.log(`terminating status worker; getting metadata for movie_id=${this.movie_id}`);
        this.status_worker.terminate();
        fetch(`/api/get-movie-metadata?api_key=${api_key}&movie_id=${this.movie_id}`, { method:'GET'})
            .then((response) => response.json())
            .then((data) => {
                console.log("movie metadata: ",data);
                this.tracking_status.text('Movie tracking complete.');
                this.download_link.show();
                // change from 'track movie' to 'retrack movie' and re-enable it
                this.track_button.val( `retrack movie.` );
                this.track_button.prop('disabled',false);

                // redraw the current frame
                const get_frame_params = {
                    api_key :api_key,
                    movie_id:this.movie_id,
                    frame_number:this.frame_number,
                    format:'json',
                };
                $.post('/api/get-frame', get_frame_params).done( (data) => {this.get_frame_handler(data);});
            });
    }

goto_frame
total_frames=${this.total_frames} last_tracked_frame=${this.last_tracked_frame}
        if (this.last_tracked_frame === null){
            return;
        }


        // if tracking, everything is disabled
        if (this.tracking) {
            this.play_button.prop('disabled',true);
            this.stop_button.prop('disabled',true);
            this.track_button.prop('disabled',true);
            this.download_button.prop('disabled',true);
            this.rotate_button.prop('disabled',true);

            $(`#${this.this_id} input.frame_movement`).prop('disabled',true); // all arrow buttons disabled
            return;
        }

            this.track_button.prop('disabled',true);
            this.download_button.prop('disabled',true);
            this.rotate_button.prop('disabled',true);
        this.stop_button.prop('disabled',true);
        this.track_button.prop('disabled', this.frame_number>=this.last_tracked_frame);
        this.download_button.prop('disabled',false);
        $(`#${this.this_id} input.frame_movement_backwards`).prop('disabled', this.frame_number<=0);
        $(`#${this.this_id} input.frame_movement_forwards`).prop('disabled', this.frame_number>=this.last_tracked_frame-1);
        this.rotate_button.prop('disabled',this.frame_number>0); // can only rotate on first frame

        // We can play if we are not on the last frame
        this.play_button.prop('disabled', this.frame_number >= this.last_tracked_frame);


    /***
     * play_button_pressed() is called when the play button is pressed, and each time the play timer clicks.
     * It goes to the next frame and sets another timer if we haven't reach the end.
     * The STOP button stops the timmer.
     */
    play_button_pressed() {
        if (this.frame_number < this.last_tracked_frame-1) {
            this.goto_frame( this.frame_number + 1);
            this.playTimer = setTimeout( () => this.play_button_pressed(), PLAY_MSEC);
            this.playing = 1;
        } else {
            this.stop_button_pressed(); // simulate stop button pressed at end of movie
            this.playing = 0;
        }
        this.set_movie_control_buttons();
    }

    stop_button_pressed() {
        if (this.playTimer) {
            clearTimeout(this.playTimer);
            this.playTimer = undefined;
        }
        this.playing = 0;
        this.set_movie_control_buttons();
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

    /***
     * get_frame_handler() is called as a callback from the /api/get-frame call.
     * It sets the frame visible in the top of the component and sets up the rest of the GUI to match.
     */
    get_frame_handler( data ) {
        //console.log('RECV get_frame_handler:',data);
        if (data.error) {
            alert(`error: ${data.message}`);
            return;
        }
        // process the /api/get-frame response
        this.last_tracked_frame = data.last_tracked_frame;
        if (this.last_tracked_frame === null){
            $(`#${this.this_id} input.frame_movement`).prop('disabled',true);
        } else {
            $(`#${this.this_id} input.frame_movement`).prop('disabled',false);
            this.frame_number_field.attr('max', data.last_tracked_frame);
        }
        this.frame_number_field.val( data.frame_number );

        //console.log("this.frame_number_field=",this.frame_number_field,"val=",this.frame_number_field.val());
        // Add the markers to the image and draw them in the table
        this.theImage = new WebImage( 0, 0, data.data_url, this);
        this.objects = [];      // clear the array
        this.objects.push(this.theImage );
        $(`#${this.this_id} td.message`).text( ' ' );
        if (data.frame_number>=0){
            if (data.frame_number == data.total_frames-1) {
                this.track_button.val( `at end of movie..` );
                this.track_button.prop('disabled',true);
            }
            else {
                this.track_button.val( `retrack from frame ${data.frame_number} to end of movie` );
                this.track_button.prop('disabled',false);
            }
        }

        // Draw trakcpoints if we have them, otherwise create initial trackpoints
        let count = 0;
        if (data.trackpoints) {
            for (let tp of data.trackpoints) {
                this.add_marker( tp.x, tp.y, tp.label );
                count += 1;
            }
        }
        if (count==0) {
            if (data.frame_number==0) {
                // Add the initial trackpoints
                this.add_marker( 20, 20, 'apex');
                this.add_marker( 20, 50, 'ruler 0 mm');
                this.add_marker( 20, 80, 'ruler 20 mm');
                this.add_marker_status.text(ADD_MARKER_STATUS_TEXT);
                this.track_button.val( "Track movie." );
                this.add_marker_status.show();
            }
        }
        this.set_movie_control_buttons();
    }
}



//const STATUS_WORKER = document.currentScript.src.replace("analyze.js","analyze_status_worker.js");
// available colors
// https://sashamaps.net/docs/resources/20-colors/
// removing green (for obvious reasons)

/* update_div:
 * Callback when data arrives from /api/get-frame.
 */

/* append_new_ptc
 * - creates the <div> that includes the canvas and is controlled by the PlantTracerController.
 * - Makes a call to get-frame to get the frame
 *   - callback gets the frame and trackpoints; it draws them and sets up the event loops to draw more.
 */
// the id for the frame that is created.
// each frame is for a specific movie
function append_new_ptc(movie_id, frame_number) {
    let this_id  = "template-" + (div_id_counter++);
    //let this_sel = `${this_id}`;
    //console.log(`append_new_ptc: frame_number=${frame_number} this_id=${this_id} this_sel=${this_sel}`);

    /* Create the <div> and a new #template. Replace the current #template with the new one. */
    let div_html = div_template
        .replace('template', `${this_id}`)
        .replace('canvas-id',`canvas-${this_id}`)
        .replace('zoom-id',`zoom-${this_id}`) + "<div id='template'></div>";
    $( '#template' ).replaceWith( div_html );
    $( '#template' )[0].scrollIntoView(); // scrolls so that the next template slot (which is empty) is in view

    // Get the movie metadata.
    // When we have it, create the plant tracer controller
    $.post('/api/get-movie-metadata', {api_key:api_key, movie_id:movie_id}).done( (data) => {
        // Create the new PlantTracerController
        //console.log("data:",data);
        if (data.error==true) {
            alert(data.message);
            return;
        }
        let window_ptc = new PlantTracerController( this_id, movie_id, frame_number, data.metadata );

        // get the request frame of the movie. When it comes back, use it to populate
        // a new PlantTracerController.
        const get_frame_params = {
            api_key :api_key,
            movie_id:movie_id,
            frame_number:frame_number,
            format:'json',
        };
        //console.log("SEND get_frame_params:",get_frame_params);
        $.post('/api/get-frame', get_frame_params).done( (data) => {
            window_ptc.get_frame_handler( data );
        });
    });
}

// Called when the page is loaded
function analyze_movie() {
    console.log("analyze_movie");
    // Say which movie we are working on
    $('#firsth2').html(`Movie #${movie_id}`);

    // capture the HTML of the <div id='#template'> into a new div
    div_template = "<div id='template'>" + $('#template').html() + "</div>";

    // erase the template div's contents, leaving an empty template at the end
    $('#template').html('');

    return append_new_ptc(movie_id, 0);           // create the first <div> and its controller
    // Prime by loading the first frame of the movie.
    // Initial drawing
}

// Call analyze_move on load
$( document ).ready( function() {
    analyze_movie();
});
