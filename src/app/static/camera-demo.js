// Standalone entry point for the Plant Tracer camera demo.
// It mounts the same capture UI as the signed-in Camera tab.
// Without a movie adapter the controller validates and discards each JPEG.
// The page needs no credentials or upload service.
// Keep this entry point and the shared assets together when hosting the demo.

import { initCamera } from './camera-capture.js?v=1';

initCamera();
