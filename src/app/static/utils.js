"use strict";
/* jshint esversion: 8 */

/**
 * Lightweight jQuery-like utility for DOM manipulation
 * Usage: $('.selector').prop('disabled', true)
 *        $('#id').html('text')
 *        $('.class').show()
 */
function $(selector) {
    // Handle $(document).ready()
    if (selector === document || (selector && selector.nodeType === 9)) {
        return {
            ready: function(callback) {
                if (document.readyState === 'loading') {
                    document.addEventListener('DOMContentLoaded', callback);
                } else {
                    callback();
                }
            }
        };
    }

    if (typeof selector === 'string') {
        // If it's a string starting with #, use getElementById for efficiency
        if (selector.startsWith('#')) {
            return new DOMWrapper(document.getElementById(selector.slice(1)));
        }
        // For class selectors, return a collection wrapper
        if (selector.startsWith('.')) {
            return new DOMCollection(document.querySelectorAll(selector));
        }
        // Otherwise use querySelector (single element)
        return new DOMWrapper(document.querySelector(selector));
    }
    // If it's already a DOM element, wrap it
    if (selector && selector.nodeType) {
        return new DOMWrapper(selector);
    }
    // Return empty wrapper for null/undefined
    return new DOMWrapper(null);
}

// Helper to work with multiple elements
function $$(selector) {
    const elements = document.querySelectorAll(selector);
    return new DOMCollection(elements);
}

// Internal helper for storing delegated listeners so `.off` can remove them.
function _storeListener(el, event, selector, handler, wrapped) {
    if (!el) return;
    if (!el._$listeners) {
        el._$listeners = [];
    }
    el._$listeners.push({ event, selector, handler, wrapped });
}

function _removeStoredListeners(el, event, selector, handler) {
    if (!el || !el._$listeners) return;
    const remaining = [];
    el._$listeners.forEach((entry) => {
        const matchEvent = !event || entry.event === event;
        const matchSelector = selector === undefined || selector === null || entry.selector === selector;
        const matchHandler = !handler || entry.handler === handler;
        if (matchEvent && matchSelector && matchHandler) {
            el.removeEventListener(entry.event, entry.wrapped);
        } else {
            remaining.push(entry);
        }
    });
    el._$listeners = remaining;
}

// Collection wrapper for multiple elements (like jQuery)
class DOMCollection {
    constructor(elements) {
        this.elements = Array.from(elements || []);
    }

    // Apply method to all elements
    show() {
        this.elements.forEach(el => {
            if (el) el.style.display = 'block';
        });
        return this;
    }

    hide() {
        this.elements.forEach(el => {
            if (el) el.style.display = 'none';
        });
        return this;
    }

    html(html) {
        if (html === undefined) {
            return this.elements[0] ? this.elements[0].innerHTML : '';
        }
        this.elements.forEach(el => {
            if (el) el.innerHTML = html;
        });
        return this;
    }

    text(text) {
        if (text === undefined) {
            return this.elements[0] ? this.elements[0].textContent : '';
        }
        this.elements.forEach(el => {
            if (el) el.textContent = text;
        });
        return this;
    }

    on(event, selectorOrHandler, maybeHandler) {
        this.elements.forEach((el) => {
            if (!el) return;
            // Delegated handler: on(event, selector, handler)
            if (typeof selectorOrHandler === 'string' && typeof maybeHandler === 'function') {
                const selector = selectorOrHandler;
                const handler = maybeHandler;
                const wrapped = function (e) {
                    const target = e.target && e.target.closest && e.target.closest(selector);
                    if (target && el.contains(target)) {
                        handler.call(target, e);
                    }
                };
                _storeListener(el, event, selector, handler, wrapped);
                el.addEventListener(event, wrapped);
            // Direct handler: on(event, handler)
            } else if (typeof selectorOrHandler === 'function') {
                const handler = selectorOrHandler;
                _storeListener(el, event, null, handler, handler);
                el.addEventListener(event, handler);
            }
        });
        return this;
    }

    off(event, selectorOrHandler, maybeHandler) {
        this.elements.forEach((el) => {
            if (!el) return;
            let selector = null;
            let handler = null;
            if (typeof selectorOrHandler === 'string') {
                selector = selectorOrHandler;
                handler = typeof maybeHandler === 'function' ? maybeHandler : null;
            } else if (typeof selectorOrHandler === 'function') {
                handler = selectorOrHandler;
            }
            _removeStoredListeners(el, event, selector, handler);
        });
        return this;
    }

    css(property, value) {
        if (typeof property === 'object') {
            this.elements.forEach(el => {
                if (el) Object.assign(el.style, property);
            });
            return this;
        }
        if (value === undefined) {
            return this.elements[0] ? window.getComputedStyle(this.elements[0])[property] : undefined;
        }
        this.elements.forEach(el => {
            if (el) el.style[property] = value;
        });
        return this;
    }

    get(index) {
        if (index === undefined) {
            return this.elements[0] || null;
        }
        return this.elements[index] || null;
    }

    hasClass(className) {
        return this.elements[0] ? this.elements[0].classList.contains(className) : false;
    }

    /**
     * Check state of the first element. Supports :visible and :hidden (jQuery-like).
     * :visible = display is not 'none' and element has layout (offsetParent or dimensions).
     * :hidden = opposite of :visible.
     */
    is(selector) {
        const el = this.elements[0];
        if (!el) return false;
        if (selector === ':visible') {
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return false;
            return el.offsetParent !== null || (el.offsetWidth > 0 && el.offsetHeight > 0);
        }
        if (selector === ':hidden') {
            return !this.is(':visible');
        }
        return false;
    }

    addClass(className) {
        this.elements.forEach(el => {
            if (el) el.classList.add(className);
        });
        return this;
    }

    removeClass(className) {
        this.elements.forEach(el => {
            if (el) el.classList.remove(className);
        });
        return this;
    }

    toggleClass(className) {
        this.elements.forEach(el => {
            if (el) el.classList.toggle(className);
        });
        return this;
    }

    one(event, handler) {
        this.elements.forEach(el => {
            if (el) el.addEventListener(event, handler, { once: true });
        });
        return this;
    }

    find(selector) {
        const found = [];
        this.elements.forEach(el => {
            if (el) {
                const matches = el.querySelectorAll(selector);
                found.push(...matches);
            }
        });
        return new DOMCollection(found);
    }

    parent() {
        const parents = this.elements.map(el => el && el.parentElement).filter(Boolean);
        return new DOMCollection(parents);
    }

    children() {
        const childLists = this.elements.map(el => el ? Array.from(el.children) : []);
        const flat = childLists.flat();
        return new DOMCollection(flat);
    }

    get length() {
        return this.elements.length;
    }
}

class DOMWrapper {
    constructor(element) {
        this.element = element;
        this.elements = element ? [element] : [];
    }

    // Property manipulation
    prop(name, value) {
        if (value === undefined) {
            // Getter
            return this.element ? this.element[name] : undefined;
        }
        // Setter
        if (this.element) {
            this.element[name] = value;
        }
        return this; // Chainable
    }

    // Attribute manipulation
    attr(name, value) {
        if (value === undefined) {
            // Getter
            return this.element ? this.element.getAttribute(name) : undefined;
        }
        // Setter
        if (this.element) {
            this.element.setAttribute(name, value);
        }
        return this; // Chainable
    }

    // Value (for form inputs)
    val(value) {
        if (value === undefined) {
            // Getter
            return this.element ? this.element.value : undefined;
        }
        // Setter
        if (this.element) {
            this.element.value = value;
        }
        return this; // Chainable
    }

    // HTML content
    html(html) {
        if (html === undefined) {
            // Getter
            return this.element ? this.element.innerHTML : '';
        }
        // Setter
        if (this.element) {
            this.element.innerHTML = html;
        }
        return this; // Chainable
    }

    // Text content
    text(text) {
        if (text === undefined) {
            // Getter
            return this.element ? this.element.textContent : '';
        }
        // Setter
        if (this.element) {
            this.element.textContent = text;
        }
        return this; // Chainable
    }

    // Show element
    show() {
        if (this.element) {
            this.element.style.display = 'block';
        }
        return this; // Chainable
    }

    // Hide element
    hide() {
        if (this.element) {
            this.element.style.display = 'none';
        }
        return this; // Chainable
    }

    // Fade in (simple show)
    fadeIn(duration) {
        if (this.element) {
            this.element.style.display = 'block';
            if (duration) {
                this.element.style.transition = `opacity ${duration}ms`;
                this.element.style.opacity = '0';
                setTimeout(() => {
                    if (this.element) this.element.style.opacity = '1';
                }, 10);
            }
        }
        return this;
    }

    // Fade out (simple hide)
    fadeOut(duration) {
        if (this.element) {
            if (duration) {
                this.element.style.transition = `opacity ${duration}ms`;
                this.element.style.opacity = '0';
                setTimeout(() => {
                    if (this.element) this.element.style.display = 'none';
                }, duration);
            } else {
                this.element.style.display = 'none';
            }
        }
        return this;
    }

    // Event listeners (supports direct and delegated: on(event, handler) or on(event, selector, handler))
    on(event, selectorOrHandler, maybeHandler) {
        if (!this.element) return this;
        // Delegated handler: on(event, selector, handler)
        if (typeof selectorOrHandler === 'string' && typeof maybeHandler === 'function') {
            const selector = selectorOrHandler;
            const handler = maybeHandler;
            const el = this.element;
            const wrapped = function (e) {
                const target = e.target && e.target.closest && e.target.closest(selector);
                if (target && el.contains(target)) {
                    handler.call(target, e);
                }
            };
            _storeListener(el, event, selector, handler, wrapped);
            el.addEventListener(event, wrapped);
        // Direct handler: on(event, handler)
        } else if (typeof selectorOrHandler === 'function') {
            const handler = selectorOrHandler;
            _storeListener(this.element, event, null, handler, handler);
            this.element.addEventListener(event, handler);
        }
        return this; // Chainable
    }

    off(event, selectorOrHandler, maybeHandler) {
        if (!this.element) return this;
        let selector = null;
        let handler = null;
        if (typeof selectorOrHandler === 'string') {
            selector = selectorOrHandler;
            handler = typeof maybeHandler === 'function' ? maybeHandler : null;
        } else if (typeof selectorOrHandler === 'function') {
            handler = selectorOrHandler;
        }
        _removeStoredListeners(this.element, event, selector, handler);
        return this; // Chainable
    }

    click(handler) {
        if (handler) {
            return this.on('click', handler);
        }
        // If no handler, trigger click
        if (this.element) {
            this.element.click();
        }
        return this;
    }

    // Get the raw DOM element
    get(index) {
        if (index !== undefined) {
            return index === 0 ? this.element : undefined;
        }
        return this.element;
    }

    // Array-like access
    get [0]() {
        return this.element;
    }

    // Support for .length property like jQuery
    get length() {
        return this.element ? 1 : 0;
    }

    // CSS manipulation
    css(property, value) {
        if (typeof property === 'object') {
            // Set multiple properties
            if (this.element) {
                Object.assign(this.element.style, property);
            }
            return this;
        }
        if (value === undefined) {
            // Getter
            return this.element ? window.getComputedStyle(this.element)[property] : undefined;
        }
        // Setter
        if (this.element) {
            this.element.style[property] = value;
        }
        return this;
    }

    hasClass(className) {
        return this.element ? this.element.classList.contains(className) : false;
    }

    /**
     * Check state of the element. Supports :visible and :hidden (jQuery-like).
     * :visible = display is not 'none' and element has layout (offsetParent or dimensions).
     * :hidden = opposite of :visible.
     */
    is(selector) {
        if (!this.element) return false;
        if (selector === ':visible') {
            const style = window.getComputedStyle(this.element);
            if (style.display === 'none' || style.visibility === 'hidden') return false;
            return this.element.offsetParent !== null ||
                (this.element.offsetWidth > 0 && this.element.offsetHeight > 0);
        }
        if (selector === ':hidden') {
            return !this.is(':visible');
        }
        return false;
    }

    addClass(className) {
        if (this.element) this.element.classList.add(className);
        return this;
    }

    removeClass(className) {
        if (this.element) this.element.classList.remove(className);
        return this;
    }

    toggleClass(className) {
        if (this.element) this.element.classList.toggle(className);
        return this;
    }

    one(event, handler) {
        if (this.element) this.element.addEventListener(event, handler, { once: true });
        return this;
    }

    find(selector) {
        if (!this.element) return new DOMCollection([]);
        return new DOMCollection(this.element.querySelectorAll(selector));
    }

    parent() {
        if (!this.element || !this.element.parentElement) return new DOMCollection([]);
        return new DOMCollection([this.element.parentElement]);
    }

    children() {
        if (!this.element) return new DOMCollection([]);
        return new DOMCollection(this.element.children);
    }
}

// Add $.post() for AJAX requests (jQuery-like API)
$.post = function(url, data) {
    let formData;
    if (data instanceof FormData) {
        formData = data;
    } else {
        formData = new FormData();
        if (typeof data === 'object') {
            for (const key in data) {
                formData.append(key, data[key]);
            }
        }
    }

    const callbacks = {
        done: [],
        fail: []
    };

    const promise = fetch(url, { method: 'POST', body: formData })
        .then(response => {
            if (!response.ok) {
                return response.text().then(text => {
                    const error = { response: response, responseText: text, status: response.status, statusText: response.statusText };
                    callbacks.fail.forEach(cb => cb(error, response.status, response.statusText));
                    throw error;
                });
            }
            return response.json();
        })
        .then(data => {
            callbacks.done.forEach(cb => cb(data));
            return data;
        })
        .catch(error => {
            if (error.response) {
                callbacks.fail.forEach(cb => cb(error, error.status || 'error', error));
            } else {
                const errObj = { responseText: error.message || String(error) };
                callbacks.fail.forEach(cb => cb(errObj, 'error', error));
            }
            throw error;
        });

    return {
        done: function(callback) {
            if (callback) callbacks.done.push(callback);
            return this;
        },
        fail: function(callback) {
            if (callback) callbacks.fail.push(callback);
            return this;
        },
        then: promise.then.bind(promise),
        catch: promise.catch.bind(promise)
    };
};

// Export for ES modules (babel transpiles to module.exports for Node/Jest)
export { $, $$, DOMWrapper };

