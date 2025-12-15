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
  presets: [['@babel/preset-env', { 
    targets: { browsers: ['last 2 versions'] },
    modules: false,  // Don't transform ES modules to CommonJS - keep as ES modules
  }]],
  plugins: [
    ['istanbul', {
      // Use absolute paths that match Jest's coverage format
      cwd: GIT_ROOT,
    }]
  ],
  retainLines: true,
  sourceType: 'module',  // Treat as ES modules, not CommonJS
};

// Get all .js and .mjs files in static directory
const jsFiles = fs.readdirSync(STATIC_DIR)
  .filter(file => file.endsWith('.js') || file.endsWith('.mjs'))
  .map(file => path.join(STATIC_DIR, file));

console.log(`Instrumenting ${jsFiles.length} JavaScript files...`);

jsFiles.forEach(filePath => {
  const fileName = path.basename(filePath);
  const sourceCode = fs.readFileSync(filePath, 'utf8');
  const outputPath = path.join(INSTRUMENTED_DIR, fileName);
  
  try {
    // For .mjs files, just copy them (babel-plugin-istanbul may not work well with ES modules)
    // For .js files, instrument them
    if (fileName.endsWith('.mjs')) {
      fs.writeFileSync(outputPath, sourceCode, 'utf8');
      console.log(`  ✓ Copied ${fileName} (ES module, not instrumented)`);
    } else {
      // Use the full path relative to git root for proper coverage path mapping
      const relativePath = path.relative(GIT_ROOT, filePath);
      const result = babel.transformSync(sourceCode, {
        ...babelConfig,
        filename: relativePath,  // Use relative path so coverage uses correct path
        // Don't add CommonJS exports - keep as ES modules for browser
        sourceType: 'module',
      });
      
      fs.writeFileSync(outputPath, result.code, 'utf8');
      console.log(`  ✓ Instrumented ${fileName}`);
    }
  } catch (error) {
    console.error(`  ✗ Error processing ${fileName}:`, error.message);
    process.exit(1);
  }
});

console.log(`\nInstrumented files written to: ${INSTRUMENTED_DIR}`);

