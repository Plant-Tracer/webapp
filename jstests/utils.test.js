/**
 * @jest-environment jsdom
 */

const { begin_inline_text_edit } = require('utils');

function buildEditableSpan() {
    document.body.innerHTML = `
        <span id="editable">Old name</span>
        <span id="editor" x-target-id="editable"></span>
    `;
    return {
        editor: document.getElementById('editor'),
        target: document.getElementById('editable'),
    };
}

describe('begin_inline_text_edit', () => {
    test('restores old text when save handler returns false', () => {
        const {editor, target} = buildEditableSpan();

        begin_inline_text_edit(editor, () => false);
        target.textContent = 'New name';
        target.dispatchEvent(new Event('blur'));

        expect(target.textContent).toBe('Old name');
    });

    test('restores old text when async save handler resolves false', async () => {
        const {editor, target} = buildEditableSpan();

        begin_inline_text_edit(editor, () => Promise.resolve(false));
        target.textContent = 'New name';
        target.dispatchEvent(new Event('blur'));
        await Promise.resolve();

        expect(target.textContent).toBe('Old name');
    });
});
