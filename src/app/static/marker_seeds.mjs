/**
 * Resolve each marker independently across the movie timeline.
 * Manual anchors and computed positions are authoritative on their own frame.
 * Display-only copies carry forward without becoming measured trackpoints.
 * A marker cannot appear before its first anchor; empty annotations end a run.
 * The index stores source references, so coordinate edits remain visible.
 * Rebuild after adding or removing an anchor, never merely for navigation.
 */
export class MarkerSeedIndex {
    constructor(frames) {
        this.frames = frames;
        this.sources = null;
    }

    invalidate() {
        this.sources = null;
    }

    forFrame(frameNumber) {
        if (!this.frames[frameNumber]) return [];
        if (!this.sources) {
            this.sources = new Map();
            this.emptyFrames = [];
            for (let index = 0; index < this.frames.length; index++) {
                const frame = this.frames[index];
                const markers = frame?.markers?.length || frame?.marker_seed_boundary
                    ? frame.markers : frame?.trim_seed_markers;
                if (!markers) continue;
                if (!markers.length && (frame.marker_seed_boundary || frame.trim_seed_markers)) {
                    this.emptyFrames.push(index);
                }
                for (const marker of markers) {
                    // Explicit false identifies a saved display copy, not an anchor.
                    // Unflagged legacy points retain their exact saved positions.
                    if (marker.is_manual === false && marker.is_traced === false) continue;
                    if (!this.sources.has(marker.label)) this.sources.set(marker.label, []);
                    this.sources.get(marker.label).push({frame: index, marker});
                }
            }
        }
        const preceding = (items, getFrame) => {
            let low = 0, high = items.length;
            while (low < high) {
                const mid = (low + high) >>> 1;
                if (getFrame(items[mid]) <= frameNumber) low = mid + 1;
                else high = mid;
            }
            return items[low - 1];
        };
        const boundary = preceding(this.emptyFrames, value => value) ?? -1;
        const markers = [];
        for (const sources of this.sources.values()) {
            const source = preceding(sources, value => value.frame);
            if (!source || source.frame < boundary) continue;
            markers.push({...source.marker, frame_number: frameNumber,
                ...(source.frame === frameNumber ? {} : {is_manual: false, is_traced: false})});
        }
        return markers;
    }
}
