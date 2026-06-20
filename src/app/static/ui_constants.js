"use strict";

const BACKEND_LAMBDA_UNRESPONSIVE_MESSAGE = 'backend lambda is unresponsive. Please report.';
const MARKER_NAME_IN_USE_MESSAGE = 'That name is in use, choose another.';
const MOVIE_CANNOT_BE_TRACED_DEMO_MESSAGE = 'Movie cannot be traced in demo mode.';
const MOVIE_IS_TRACED_MESSAGE = 'Movie is traced!';
const TRACE_MOVIE = 'Trace movie';
const MOVIE_IS_TRACED_RETRACE_AS_NEEDED_MESSAGE = `${MOVIE_IS_TRACED_MESSAGE} Check for errors and retrace as necessary.`;
const MOVIE_READY_FOR_INITIAL_TRACING_MESSAGE = 'Movie ready for initial tracing.';
const MOVIE_READY_FOR_TRACING_MESSAGE = 'Movie ready for tracing.';
const MOVIE_READY_PLACE_MARKERS_TRACE_MESSAGE = `${MOVIE_READY_FOR_TRACING_MESSAGE} Place markers and click ${TRACE_MOVIE}.`;
const PLACE_MARKERS_TRACE_START_MESSAGE = `Place markers and click ${TRACE_MOVIE} to start tracing.`;
const PRESS_PLAY_STATUS_TEXT = 'Press play';
const RETRACE_REQUIRED_MESSAGE = 'marker moved; movie may require retracing';
const RETRACE_MOVIE = 'Retrace movie';
const RETRACE_TO_END_OF_MOVIE = 'Retrace to end of movie';
const RESET_TRACING_CONFIRM_MESSAGE = 'Are you sure you want to delete all of the work and reset to the first frame?';
const TRACE_TO_END_OF_MOVIE = 'Trace to end of movie';
const TRACE_MOVIE_TRIM_DISABLED_TITLE = `${TRACE_MOVIE} to enable trimming.`;
const TRACING_COMPLETE_LOADING_MOVIE_MESSAGE = 'Tracing complete. Loading movie...';
const TRACING_STARTING_MESSAGE = 'Tracing starting...';

export {
    BACKEND_LAMBDA_UNRESPONSIVE_MESSAGE,
    MARKER_NAME_IN_USE_MESSAGE,
    MOVIE_CANNOT_BE_TRACED_DEMO_MESSAGE,
    MOVIE_IS_TRACED_MESSAGE,
    MOVIE_IS_TRACED_RETRACE_AS_NEEDED_MESSAGE,
    MOVIE_READY_FOR_INITIAL_TRACING_MESSAGE,
    MOVIE_READY_FOR_TRACING_MESSAGE,
    MOVIE_READY_PLACE_MARKERS_TRACE_MESSAGE,
    PLACE_MARKERS_TRACE_START_MESSAGE,
    PRESS_PLAY_STATUS_TEXT,
    RETRACE_MOVIE,
    RETRACE_REQUIRED_MESSAGE,
    RETRACE_TO_END_OF_MOVIE,
    RESET_TRACING_CONFIRM_MESSAGE,
    TRACE_MOVIE,
    TRACE_TO_END_OF_MOVIE,
    TRACE_MOVIE_TRIM_DISABLED_TITLE,
    TRACING_COMPLETE_LOADING_MOVIE_MESSAGE,
    TRACING_STARTING_MESSAGE,
};
