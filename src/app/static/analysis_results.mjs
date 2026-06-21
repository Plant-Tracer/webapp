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
 * Rate (displacement per unit time) is intentionally NOT computed here yet; the
 * frame->time conversion is unresolved (see #986) and tracked as a follow-up.
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
                                lastInflection = null, scale = 1 } = {}) {
    if (!is_point(firstTip) || !is_point(lastTip)) {
        return { distance: null, angle: null };
    }
    const distance = distance_between(firstTip, lastTip) * scale;
    const angle = inflection_angle(firstTip, lastTip, firstInflection, lastInflection);
    return { distance, angle };
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
 * @param {Array}  tipPoints  tip positions {x, y} across all (trimmed) frames
 * @param {number} scale      mm/pixel (default 1 = pixels)
 *
 * Returns { maxAmplitude } = (max x - min x) * scale, or null when there are no points.
 */
function circumnutation_results({ tipPoints = [], scale = 1 } = {}) {
    const xs = (tipPoints || []).filter(is_point).map(p => Number(p.x));
    if (xs.length === 0) {
        return { maxAmplitude: null };
    }
    const maxAmplitude = (Math.max(...xs) - Math.min(...xs)) * scale;
    return { maxAmplitude };
}

export { gravitropism_results, circumnutation_results, inflection_angle, distance_between };
