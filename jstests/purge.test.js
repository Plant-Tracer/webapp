/**
 * @jest-environment jsdom
 */

const module = require('planttracer')
const purge_movie = module.purge_movie

describe('purge_movie', () => {
    beforeEach(() => {
        document.body.innerHTML = [
            '<a id="delete_movie_link"></a>',
            '<div id="upload_message"></div>',
            '<div id="upload-preview"></div>',
            '<h2 id="upload-form-title"></h2>',
            '<div id="upload-instructions"></div>',
            '<form id="upload-movie-form"></form>'
        ].join('');
        window.movie_id = 'movie-123';
        global.api_key = 'api-key';
        global.API_BASE = '/';
        global.fetch = jest.fn().mockResolvedValue({
            ok: true,
            json: async () => ({error: false})
        });
    });

    afterEach(() => {
        jest.clearAllMocks();
    });

    test('deletes the uploaded movie and restores the upload form', async () => {
        await purge_movie();

        expect(fetch).toHaveBeenCalledWith('/api/delete-movie', expect.objectContaining({
            method: 'POST'
        }));
        const formData = fetch.mock.calls[0][1].body;
        expect(formData.get('api_key')).toBe('api-key');
        expect(formData.get('movie_id')).toBe('movie-123');
        expect(window.movie_id).toBeNull();
        expect(document.querySelector('#upload_message').textContent).toBe(
            'Movie deleted. You can upload another movie.'
        );
        expect(document.querySelector('#upload-preview').style.display).toBe('none');
    });

    test('keeps the movie available when deletion fails', async () => {
        fetch.mockResolvedValueOnce({
            ok: false,
            json: async () => ({error: true, message: 'Not authorized'})
        });

        await purge_movie();

        expect(window.movie_id).toBe('movie-123');
        expect(document.querySelector('#delete_movie_link').getAttribute('aria-disabled')).toBeNull();
        expect(document.querySelector('#upload_message').textContent).toBe(
            'Unable to delete movie: Not authorized'
        );
    });
});
