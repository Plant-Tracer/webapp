import { enableFetchMocks } from 'jest-fetch-mock';
enableFetchMocks();
import 'regenerator-runtime/runtime';

const { TextEncoder, TextDecoder } = require('util');

if (typeof global.TextEncoder === 'undefined') {
  global.TextEncoder = TextEncoder;
}
if (typeof global.TextDecoder === 'undefined') {
  global.TextDecoder = TextDecoder;
}