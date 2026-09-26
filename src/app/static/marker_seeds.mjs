/** Resolve display/trace seeds without adding synthetic points to saved frame data. */
export function frameMarkerSeeds(frames, frameNumber, tracedThrough = -1) {
    const target = frames[frameNumber];
    if (!target) return [];
    if (!target.markers?.length && frameNumber <= tracedThrough) return [];
    for (let index = frameNumber; index >= 0; index--) {
        const markers = frames[index]?.markers || [];
        if (markers.length) {
            return markers.map(marker => ({...marker, frame_number: frameNumber}));
        }
        // Do not revive markers that disappeared at the end of an existing trace.
        if (index <= tracedThrough) return [];
    }
    return [];
}
