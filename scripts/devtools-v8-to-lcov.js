#!/usr/bin/env node
"use strict";

/**
 * Convert Chrome DevTools V8 coverage JSON (Profiler.takePreciseCoverage)
 * produced by tests/js_v8_coverage.py into an LCOV file using the
 * v8-to-istanbul and Istanbul reporting libraries.
 *
 * Usage:
 *   node scripts/devtools-v8-to-lcov.js \
 *     coverage/browser-v8-coverage.json \
 *     coverage/browser-v8-coverage.lcov
 */

const fs = require("fs");
const path = require("path");

const v8ToIstanbul = require("v8-to-istanbul");
const libCoverage = require("istanbul-lib-coverage");
const libReport = require("istanbul-lib-report");
const reports = require("istanbul-reports");

function usageAndExit() {
  // eslint-disable-next-line no-console
  console.error(
    "Usage: node scripts/devtools-v8-to-lcov.js <input-json> <output-lcov>"
  );
  process.exit(1);
}

async function main() {
  const [inputJson, outputLcov] = process.argv.slice(2);
  if (!inputJson || !outputLcov) {
    usageAndExit();
  }

  if (!fs.existsSync(inputJson)) {
    // eslint-disable-next-line no-console
    console.error(`Input coverage file not found: ${inputJson}`);
    process.exit(1);
  }

  const raw = fs.readFileSync(inputJson, "utf8");
  let data;
  try {
    data = JSON.parse(raw);
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error("Failed to parse V8 coverage JSON:", err.message || err);
    process.exit(1);
  }

  const entries = Array.isArray(data.result) ? data.result : [];
  if (entries.length === 0) {
    // Nothing to do; exit successfully.
    return;
  }

  const coverageMap = libCoverage.createCoverageMap({});

  for (const entry of entries) {
    const url = entry.url || "";
    const functions = Array.isArray(entry.functions) ? entry.functions : [];
    
    // Log entries that contain planttracer.js for debugging coverage issues
    if (url.includes('planttracer.js')) {
      // eslint-disable-next-line no-console
      console.log(`Processing planttracer.js entry: ${functions.length} functions`);
      // Log function names and their coverage counts
      for (const fn of functions.slice(0, 5)) {
        const fnName = fn.functionName || '(anonymous)';
        const ranges = fn.ranges || [];
        const totalCount = ranges.reduce((sum, r) => sum + (r.count || 0), 0);
        // eslint-disable-next-line no-console
        console.log(`  - ${fnName}: ${ranges.length} ranges, total count=${totalCount}`);
      }
      if (functions.length > 5) {
        // eslint-disable-next-line no-console
        console.log(`  ... and ${functions.length - 5} more functions`);
      }
    }
    
    if (!url || functions.length === 0) {
      continue;
    }

    // Map DevTools URL (e.g., http://127.0.0.1:8765/static/foo.mjs) to the
    // local source file path under src/app/static.
    const localFile = mapUrlToLocalFile(url);
    if (!localFile || !fs.existsSync(localFile)) {
      // eslint-disable-next-line no-console
      console.warn(`Skipping coverage for URL (no local file): ${url}`);
      continue;
    }

    const source = fs.readFileSync(localFile, "utf8");

    // Use a path relative to the repository root so that it matches Jest coverage.
    // This ensures Codecov can properly merge V8 browser coverage with Jest unit test coverage.
    const repoRoot = path.join(__dirname, "..");
    const relativePath = path.relative(repoRoot, localFile);

    // v8-to-istanbul expects a file path and the original source.
    const converter = v8ToIstanbul(relativePath, 0, { source });
    // load() parses the source and prepares for coverage application.
    // eslint-disable-next-line no-await-in-loop
    await converter.load();
    converter.applyCoverage(functions);

    const fileCoverage = converter.toIstanbul();
    // v8-to-istanbul returns an object compatible with Istanbul's
    // coverage map; merge it rather than treating it as a single
    // FileCoverage instance.
    coverageMap.merge(fileCoverage);
  }

  // If we have no mapped files, quietly succeed.
  if (coverageMap.files().length === 0) {
    return;
  }

  const outDir = path.dirname(outputLcov);
  const outFile = path.basename(outputLcov);

  fs.mkdirSync(outDir, { recursive: true });

  const context = libReport.createContext({
    dir: outDir,
    coverageMap,
  });

  // lcovonly reporter writes a single LCOV file.
  const report = reports.create("lcovonly", { file: outFile });
  report.execute(context);
}

/**
 * Map a DevTools script URL to a local source file path.
 *
 * Example:
 *   http://127.0.0.1:8765/static/canvas_controller.mjs
 *   -> src/app/static/canvas_controller.mjs
 */
function mapUrlToLocalFile(url) {
  try {
    const u = new URL(url);
    // Expect paths like /static/filename or /static/subdir/filename.
    const prefix = "/static/";
    if (!u.pathname.startsWith(prefix)) {
      return null;
    }
    const relative = u.pathname.slice(prefix.length); // drop leading /static/
    return path.join(__dirname, "..", "src", "app", "static", relative);
  } catch (_err) {
    // Non-URL strings (e.g. inline scripts) are ignored.
    return null;
  }
}

main().catch((err) => {
  // eslint-disable-next-line no-console
  console.error("Error while generating LCOV from V8 coverage:", err);
  process.exit(1);
});
