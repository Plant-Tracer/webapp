import { enableFetchMocks } from 'jest-fetch-mock';
enableFetchMocks();
import 'regenerator-runtime/runtime';

const fs = require('fs');
const path = require('path');
const { TextEncoder, TextDecoder } = require('util');

if (typeof global.TextEncoder === 'undefined') {
  global.TextEncoder = TextEncoder;
}

if (typeof global.TextDecoder === 'undefined') {
  global.TextDecoder = TextDecoder;
}

if (typeof window !== 'undefined' && typeof window.jQuery === 'undefined') {
  const jqueryPath = path.join(process.cwd(), 'src', 'app', 'static', 'jquery-3.7.1.min.js');
  const jquerySource = fs.readFileSync(jqueryPath, 'utf8');
  window.eval(jquerySource);
  global.$ = window.$;
  global.jQuery = window.jQuery;
}
