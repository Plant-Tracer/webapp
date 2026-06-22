"use strict";

/* eslint-env es6 */
/* see eslint.config for globals */
/* jshint esversion: 8 */

/*
 * analysis_results.mjs
 *
 * Pure (DOM-free, unit-testable) aggregate trace-result statistics, ported from the
 * legacy iOS app's Graph.js showResult(). See docs/Development/AnalysisResults.rst and
 * issue #986.
 *
 * Two result groups:
 *   - Gravitropism: Distance (first->last tip displacement) and Angle (bend at the
 *     Inflection Point pivot, via the law of cosines).
 *   - Circumnutation: Max Amplitude (horizontal x-range of the tip over all frames).
 *
 * Rate (displacement per unit time) is computed from the capture interval `fpm`
 * (frames/minute, see #1056): elapsed_time(min) = frame_span / fpm. When fpm is not set,
 * Rate is expressed per frame instead of per minute (the `rateTimeUnit` field is
 * 'min' or 'frame' accordingly). See #1053.
 *
 * All inputs are points of the form {x, y} in a single consistent coordinate space.
 * `scale` converts pixels to physical units (mm/pixel); pass 1 for pixels. Distance and
 * Max Amplitude scale linearly; Angle is scale-invariant (the factor cancels), so it is
 * always computed in the raw coordinate space.
 */

function distance_between(a, b) {
    return Math.hypot(b.x - a.x, b.y - a.y);
}

function is_point(p) {
    return p && Number.isFinite(Number(p.x)) && Number.isFinite(Number(p.y));
}

function rate_time_unit(fpm) {
    return (fpm != null && Number(fpm) > 0) ? 'min' : 'frame';
}

function frame_span(a, b) {
    if (a == null || b == null || !Number.isFinite(Number(a)) || !Number.isFinite(Number(b))) {
        return null;
    }
    return Math.abs(Number(b) - Number(a));
}

/*
 * Rate of a magnitude over an elapsed frame span. With a positive fpm, the span is
 * converted to minutes (span / fpm); otherwise the span stays in frames. Returns
 * { rate, rateTimeUnit } where rate is null when it cannot be computed (no span, or a
 * zero-length span — e.g. the x extremes fall on the same frame).
 */
function elapsed_rate(magnitude, elapsedFrames, fpm) {
    const rateTimeUnit = rate_time_unit(fpm);
    if (magnitude == null || elapsedFrames == null) {
        return { rate: null, rateTimeUnit };
    }
    const elapsed = rateTimeUnit === 'min' ? elapsedFrames / Number(fpm) : elapsedFrames;
    const rate = elapsed > 0 ? magnitude / elapsed : null;
    return { rate, rateTimeUnit };
}

/*
 * Gravitropism results.
 *
 * @param {object}  firstTip        tip position in the first frame {x, y}
 * @param {object}  lastTip         tip position in the last frame {x, y}
 * @param {object?} firstInflection inflection-point position in the first frame {x, y}
 * @param {object?} lastInflection  inflection-point position in the last frame {x, y}
 * @param {number}  scale           mm/pixel (default 1 = pixels)
 *
 * Returns { distance, angle } where angle is in degrees, or null when no inflection
 * point is available or the angle is degenerate (a tip coincides with the inflection
 * point, making the triangle undefined).
 */
function gravitropism_results({ firstTip, lastTip, firstInflection = null,
                                lastInflection = null, scale = 1,
                                firstFrameNumber = null, lastFrameNumber = null, fpm = null } = {}) {
    if (!is_point(firstTip) || !is_point(lastTip)) {
        return { distance: null, angle: null, rate: null, rateTimeUnit: rate_time_unit(fpm) };
    }
    const distance = distance_between(firstTip, lastTip) * scale;
    const angle = inflection_angle(firstTip, lastTip, firstInflection, lastInflection);
    const { rate, rateTimeUnit } = elapsed_rate(distance, frame_span(firstFrameNumber, lastFrameNumber), fpm);
    return { distance, angle, rate, rateTimeUnit };
}

/*
 * Bend angle (degrees) at the inflection pivot, via the law of cosines.
 * b = first tip -> first inflection, c = last tip -> last inflection,
 * a = first tip -> last tip. Computed in raw coordinates (scale cancels).
 * Returns null when no inflection point is available or the triangle is degenerate.
 */
function inflection_angle(firstTip, lastTip, firstInflection, lastInflection) {
    if (!is_point(firstInflection) || !is_point(lastInflection)) {
        return null;
    }
    const b = distance_between(firstTip, firstInflection);
    const c = distance_between(lastTip, lastInflection);
    const a = distance_between(firstTip, lastTip);
    if (b === 0 || c === 0) {
        return null;
    }
    let cos_angle = (b * b + c * c - a * a) / (2 * b * c);
    // Guard against floating-point drift outside the valid acos domain.
    cos_angle = Math.max(-1, Math.min(1, cos_angle));
    return Math.acos(cos_angle) * 180 / Math.PI;
}

/*
 * Circumnutation results.
 *
 * @param {Array}  tipPoints  tip positions {x, y, frame_number} across all (trimmed) frames
 * @param {number} scale      mm/pixel (default 1 = pixels)
 * @param {number} fpm        capture interval in frames/minute (null/0 => Rate per frame)
 *
 * Returns { maxAmplitude, rate, rateTimeUnit }. maxAmplitude = (max x - min x) * scale.
 * Rate = maxAmplitude / elapsed time between the x-extreme frames (legacy semantics); it is
 * null when there are no points or the extremes fall on the same frame.
 */
function circumnutation_results({ tipPoints = [], scale = 1, fpm = null } = {}) {
    const points = (tipPoints || []).filter(is_point);
    if (points.length === 0) {
        return { maxAmplitude: null, rate: null, rateTimeUnit: rate_time_unit(fpm) };
    }
    let minPoint = points[0];
    let maxPoint = points[0];
    for (const point of points) {
        if (Number(point.x) < Number(minPoint.x)) {
            minPoint = point;
        }
        if (Number(point.x) > Number(maxPoint.x)) {
            maxPoint = point;
        }
    }
    const maxAmplitude = (Number(maxPoint.x) - Number(minPoint.x)) * scale;
    const { rate, rateTimeUnit } = elapsed_rate(
        maxAmplitude, frame_span(minPoint.frame_number, maxPoint.frame_number), fpm);
    return { maxAmplitude, rate, rateTimeUnit };
}

export { gravitropism_results, circumnutation_results, inflection_angle, distance_between };
