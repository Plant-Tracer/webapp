/**
 * @jest-environment jsdom
 */


const $ = require('jquery');
global.$ = $;

const module = require('../static/planttracer.js')
const purge_movie = module.purge_movie

describe('purge_movie', () => {
    // Mock console.log
    beforeEach(() => {
        jest.spyOn(global.console, 'log').mockImplementation(() => {});
    });

    afterEach(() => {
        jest.clearAllMocks();
    });

    test('should log "purge_movie()" to the console', () => {
        purge_movie();
        expect(console.log).toHaveBeenCalledWith("purge_movie()");
    });
});
