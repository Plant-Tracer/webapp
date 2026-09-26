/** Index display/trace seeds without adding synthetic points to saved frame data. */
export class MarkerSeedIndex {
    constructor(frames) {
        this.frames = frames;
        this.preceding = null;
    }

    invalidate() {
        this.preceding = null;
    }

    forFrame(frameNumber, tracedThrough = -1) {
        const target = this.frames[frameNumber];
        if (!target) return [];
        if (!this.preceding) {
            this.preceding = new Int32Array(this.frames.length);
            let previous = -1;
            for (let index = 0; index < this.frames.length; index++) {
                if (this.frames[index]?.markers?.length) previous = index;
                this.preceding[index] = previous;
            }
        }
        const source = this.preceding[frameNumber];
        // Keep gaps in an existing trace, including an empty tracing frontier.
        if (source < 0 || (!target.markers?.length
            && (frameNumber <= tracedThrough || source < tracedThrough))) return [];
        return (this.frames[source].markers || [])
            .map(marker => ({...marker, frame_number: frameNumber}));
    }
}
