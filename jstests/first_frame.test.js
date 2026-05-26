/**
 * @jest-environment jsdom
 */

const module = require('planttracer')
const first_frame_url = module.first_frame_url


describe('first_frame_url', () => {
    const LAMBDA_API_BASE = 'https://lambda.planttracer.com/';
    const api_key = 'abcdefghijklmnopqrstuvwxyz';
    const movie_id = '600';

    beforeEach(() => {
        global.LAMBDA_API_BASE = LAMBDA_API_BASE;
        global.api_key = api_key;
    });

    test('should return lambda-resize get-frame URL with api_key, movie_id, and size=analysis', () => {
        const result = first_frame_url(movie_id);
        expect(result).toContain('resize-api/v1/first-frame');
        expect(result).toContain(`api_key=${api_key}`);
        expect(result).toContain(`movie_id=${movie_id}`);
    });

    test('should include a timestamp in the URL', () => {
        const result = first_frame_url(movie_id);
    });

    test('should include the correct movie ID in the URL', () => {
        const result = first_frame_url('test_movie');
        expect(result).toContain('movie_id=test_movie');
    });
});
