/**
 * @jest-environment jsdom
 */


const $ = require('jquery');
global.$ = $;

// Import the computeSHA256 function from the appropriate path
const module = require('../static/planttracer.js');
const computeSHA256 = module.computeSHA256
const { TextEncoder } = require('util'); 

// Mock File object for testing
class MockFile {
    constructor(content, type) {
        this.content = content;
        this.type = type;
    }

    async arrayBuffer() {
        return new TextEncoder().encode(this.content).buffer;
    }
}

// Test suite for computeSHA256
describe('computeSHA256', () => {
    
    it('should return the correct SHA-256 hash for a known file', async () => {
        const fileContent = 'Hello, World!';  // Known content
        const expectedHash = 'dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f'; // Precomputed SHA-256 for "Hello, World!"
        const mockFile = new MockFile(fileContent, 'text/plain');

        const result = await computeSHA256(mockFile);

        expect(result).toBe(expectedHash);
    });

    it('should return the SHA-256 hash for an empty file', async () => {
        const mockFile = new MockFile('', 'text/plain');
        const expectedHash = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855';  // SHA-256 of empty input

        const result = await computeSHA256(mockFile);

        expect(result).toBe(expectedHash);
    });

});
