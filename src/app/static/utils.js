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

    on(event, handler) {
        this.elements.forEach(el => {
            if (el) el.addEventListener(event, handler);
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

    // Event listeners
    on(event, handler) {
        if (this.element) {
            this.element.addEventListener(event, handler);
        }
        return this; // Chainable
    }

    off(event, handler) {
        if (this.element) {
            this.element.removeEventListener(event, handler);
        }
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

// Make $ available globally
if (typeof window !== 'undefined') {
    window.$ = $;
    window.$$ = $$;
}

// Export for Node.js environments
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { $, $$, DOMWrapper };
}

