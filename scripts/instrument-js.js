#!/usr/bin/env node
/**
 * Simple JavaScript file copier for browser tests.
 *
 * This script mirrors files from src/app/static to src/app/static-instrumented
 * without applying any instrumentation or transformation. It exists so that
 * older tooling expecting a static-instrumented directory continues to work
 * after removal of Istanbul-based coverage.
 */

const fs = require('fs');
const path = require('path');

const STATIC_DIR = path.join(__dirname, '..', 'src', 'app', 'static');
const INSTRUMENTED_DIR = path.join(__dirname, '..', 'src', 'app', 'static-instrumented');

if (!fs.existsSync(INSTRUMENTED_DIR)) {
	fs.mkdirSync(INSTRUMENTED_DIR, { recursive: true });
}

const jsFiles = fs.readdirSync(STATIC_DIR)
	.filter(file => file.endsWith('.js') || file.endsWith('.mjs'));

console.log(`Copying ${jsFiles.length} JavaScript files to static-instrumented...`);

jsFiles.forEach(fileName => {
	const src = path.join(STATIC_DIR, fileName);
	const dest = path.join(INSTRUMENTED_DIR, fileName);
	fs.copyFileSync(src, dest);
	console.log(`  ✓ Copied ${fileName}`);
});

console.log(`\nInstrumented files written to: ${INSTRUMENTED_DIR}`);
