/**
 * @jest-environment jsdom
 */
const { check_upload_metadata, upload_movie } = require('planttracer');

function selectFile(size) {
    // Supply file metadata without allocating a 256 MiB test payload.
    const file = new File(['movie'], 'plant.mp4', {type: 'video/mp4'});
    Object.defineProperty(file, 'size', {value: size});
    Object.defineProperty(document.querySelector('#movie-file'), 'files', {
        value: [file], configurable: true,
    });
}

beforeEach(() => {
    document.body.innerHTML = `
        <form id="upload-movie-form">
            <input id="movie-title" value="Plant movie">
            <input id="movie-description" value="Plant growth">
            <input id="movie-file" type="file">
            <button id="upload-button" type="button"></button>
            <span id="upload-size-error"></span>
        </form>
        <div id="message"></div>`;
    global.MAX_FILE_UPLOAD = 256 * 1024 * 1024;
    fetch.resetMocks();
    selectFile(100);
});

test.each(['#movie-title', '#movie-description'])('requires at least three characters in %s', selector => {
    document.querySelector(selector).value = 'ab';
    check_upload_metadata();
    expect(document.querySelector('#upload-button').disabled).toBe(true);
});

test('requires a selected file', () => {
    Object.defineProperty(document.querySelector('#movie-file'), 'files', {value: [], configurable: true});
    check_upload_metadata();
    expect(document.querySelector('#upload-button').disabled).toBe(true);
});

test.each([256 * 1024 * 1024 - 1, 256 * 1024 * 1024])('allows a file of %i bytes', size => {
    selectFile(size);
    check_upload_metadata();
    expect(document.querySelector('#upload-button').disabled).toBe(false);
    expect(document.querySelector('#upload-size-error').textContent).toBe('');
});

test('disables oversized uploads and clears the error when a smaller file is selected', () => {
    selectFile(MAX_FILE_UPLOAD + 1);
    check_upload_metadata();
    expect(document.querySelector('#upload-button').disabled).toBe(true);
    expect(document.querySelector('#upload-size-error').textContent).toBe('Choose a movie of 256 MiB or less.');
    // Editing the title must not reenable upload for the oversized file.
    document.querySelector('#movie-title').value = 'Another movie';
    check_upload_metadata();
    expect(document.querySelector('#upload-button').disabled).toBe(true);
    selectFile(MAX_FILE_UPLOAD);
    check_upload_metadata();
    expect(document.querySelector('#upload-button').disabled).toBe(false);
    expect(document.querySelector('#upload-size-error').textContent).toBe('');
});

test('direct upload invocation also rejects oversized files before any network request', () => {
    selectFile(MAX_FILE_UPLOAD + 1);
    upload_movie();
    expect(fetch).not.toHaveBeenCalled();
    expect(document.querySelector('#message').textContent).toBe('Choose a movie of 256 MiB or less.');
    expect(document.querySelector('#upload-button').disabled).toBe(true);
    expect(document.querySelector('#upload-movie-form').style.display).not.toBe('none');
});
