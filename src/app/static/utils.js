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

function begin_inline_text_edit(editor, onChange) {
    const target = editor.getAttribute('x-target-id');
    const targetElement = $(`#${target}`).get(0);
    const oldValue = targetElement.textContent;
    let finished = false;

    targetElement.setAttribute('contenteditable','true');
    targetElement.focus();

    function finished_editing() {
        if (finished) {
            return;
        }
        finished = true;
        targetElement.setAttribute('contenteditable','false');
        targetElement.blur();
        const value = targetElement.textContent;
        if (value != oldValue) {
            onChange(targetElement, value, oldValue);
        }
    }

    targetElement.addEventListener('keydown', function(event) {
        if (event.keyCode == 9 || event.keyCode == 13) {
            finished_editing();
        } else if (event.keyCode == 27) {
            targetElement.textContent = oldValue;
            targetElement.blur();
            targetElement.setAttribute('contenteditable','false');
            finished = true;
        }
    });
    targetElement.addEventListener('blur', function(_event) {
        finished_editing();
    }, {once: true});
}

export { $, begin_inline_text_edit };
