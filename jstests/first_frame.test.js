/**
 * @jest-environment jsdom
 */


const $ = require('jquery');
global.$ = $;

const module = require('../static/planttracer.js')
const first_frame_url = module.first_frame_url


describe('first_frame_url', () => {
    // Mock API base URL and API key
    const API_BASE = 'https://planttracer.com';
    const api_key = 'abcdefghijklmnopqrstuvwxyz';
    const movie_id = '600';
    
    // Mock Date object to control the timestamp
    beforeEach(() => {
        global.API_BASE = API_BASE;
        global.api_key = api_key;
    });

    test('should return a URL containing API base, api_key, and movie_id', () => {
        const result = first_frame_url(movie_id);
        // Check that the URL contains the base, api_key, movie_id, frame_number, and format
        expect(result).toContain(`${API_BASE}api/get-frame?api_key=${api_key}&movie_id=${movie_id}&frame_number=0&format=jpeg`);
    });

    test('should include a timestamp in the URL', () => {
        const result = first_frame_url(movie_id);
        // Use regex to check that t= is followed by a numeric timestamp
        expect(result).toMatch(/t=\d+/);
    });
    
    test('should include the correct movie ID in the URL', () => {
        const result = first_frame_url('test_movie');
        expect(result).toContain('movie_id=test_movie');
    });
});

