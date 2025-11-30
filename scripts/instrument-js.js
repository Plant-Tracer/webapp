#!/usr/bin/env node
/**
 * Instrument JavaScript files for coverage collection in browser tests.
 * This script uses babel with istanbul plugin to instrument JS files.
 */

const fs = require('fs');
const path = require('path');
const babel = require('@babel/core');

const STATIC_DIR = path.join(__dirname, '..', 'src', 'app', 'static');
const INSTRUMENTED_DIR = path.join(__dirname, '..', 'src', 'app', 'static-instrumented');
const GIT_ROOT = path.join(__dirname, '..');

// Ensure instrumented directory exists
if (!fs.existsSync(INSTRUMENTED_DIR)) {
  fs.mkdirSync(INSTRUMENTED_DIR, { recursive: true });
}

// Babel config for instrumentation
const babelConfig = {
  presets: [['@babel/preset-env', { targets: { browsers: ['last 2 versions'] } }]],
  plugins: [
    ['istanbul', {
      // Use absolute paths that match Jest's coverage format
      cwd: GIT_ROOT,
    }]
  ],
  retainLines: true,
};

// Get all .js files in static directory
const jsFiles = fs.readdirSync(STATIC_DIR)
  .filter(file => file.endsWith('.js'))
  .map(file => path.join(STATIC_DIR, file));

console.log(`Instrumenting ${jsFiles.length} JavaScript files...`);

jsFiles.forEach(filePath => {
  const fileName = path.basename(filePath);
  const sourceCode = fs.readFileSync(filePath, 'utf8');
  
  try {
    // Use the full path relative to git root for proper coverage path mapping
    const relativePath = path.relative(GIT_ROOT, filePath);
    const result = babel.transformSync(sourceCode, {
      ...babelConfig,
      filename: relativePath,  // Use relative path so coverage uses correct path
    });
    
    const outputPath = path.join(INSTRUMENTED_DIR, fileName);
    fs.writeFileSync(outputPath, result.code, 'utf8');
    console.log(`  ✓ Instrumented ${fileName}`);
  } catch (error) {
    console.error(`  ✗ Error instrumenting ${fileName}:`, error.message);
    process.exit(1);
  }
});

console.log(`\nInstrumented files written to: ${INSTRUMENTED_DIR}`);

