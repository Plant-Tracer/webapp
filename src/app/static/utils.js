"use strict";

/*
 * Module shim for the globally loaded jQuery instance.
 *
 * Browser pages load jquery-3.7.1.min.js as a classic script so `$` and
 * `jQuery` exist on `window`. Our ES modules import `$` from here so module
 * code and classic inline code use the same implementation.
 */

const $ = window.jQuery || window.$;

if (!$) {
    throw new Error("jQuery is not available. Load jquery-3.7.1.min.js before importing utils.js.");
}

export { $ };
