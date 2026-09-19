/** Exact frame access with bounded decoded storage; compressed samples stay in decode order. */
import { createFile } from './mp4box.all.js';

const MAX_ENCODED_BYTES = 256 * 1024 * 1024;
const MAX_GROUP_BYTES = 128 * 1024 * 1024;
const MICROSECONDS_PER_SECOND = 1000000;

function avcDecoderDescription(avcC) {
  const spsLength = avcC.SPS.reduce((total, sps) => total + 2 + sps.length, 0);
  const ppsLength = avcC.PPS.reduce((total, pps) => total + 2 + pps.length, 0);
  const extLength = avcC.ext ? avcC.ext.length : 0;
  const bytes = new Uint8Array(7 + spsLength + ppsLength + extLength);
  const view = new DataView(bytes.buffer);
  let offset = 0;
  bytes[offset] = avcC.configurationVersion;
  offset += 1;
  bytes[offset] = avcC.AVCProfileIndication;
  offset += 1;
  bytes[offset] = avcC.profile_compatibility;
  offset += 1;
  bytes[offset] = avcC.AVCLevelIndication;
  offset += 1;
  bytes[offset] = 0xfc | avcC.lengthSizeMinusOne;
  offset += 1;
  bytes[offset] = 0xe0 | avcC.SPS.length;
  offset += 1;
  for (const sps of avcC.SPS) {
    view.setUint16(offset, sps.length);
    offset += 2;
    bytes.set(sps.data, offset);
    offset += sps.length;
  }
  bytes[offset] = avcC.PPS.length;
  offset += 1;
  for (const pps of avcC.PPS) {
    view.setUint16(offset, pps.length);
    offset += 2;
    bytes.set(pps.data, offset);
    offset += pps.length;
  }
  if (avcC.ext) {
    bytes.set(avcC.ext, offset);
  }
  return bytes;
}

function extractMp4Samples(arrayBuffer) {
  return new Promise((resolve, reject) => {
    const mp4boxfile = createFile();
    const samples = [];
    let videoTrack = null;

    mp4boxfile.onError = (error) => {
      reject(new Error(String(error)));
    };

    mp4boxfile.onReady = (info) => {
      videoTrack = info.tracks.find((track) => track.video);
      if (!videoTrack) {
        reject(new Error('No video track found.'));
        return;
      }
      mp4boxfile.onSamples = (_id, _user, newSamples) => {
        samples.push(...newSamples);
      };
      mp4boxfile.setExtractionOptions(videoTrack.id, null, {
        nbSamples: 1000,
        rapAlignement: false,
      });
      mp4boxfile.start();
    };

    arrayBuffer.fileStart = 0;
    mp4boxfile.appendBuffer(arrayBuffer);
    mp4boxfile.flush();

    if (videoTrack) {
      resolve({ samples, videoTrack });
    } else {
      reject(new Error('No video track metadata found.'));
    }
  });
}

function videoFrameType(sample) {
  return sample.is_sync || sample.is_rap ? 'key' : 'delta';
}

function samplesInDecodeOrder(samples) {
  return [...samples].sort((left, right) => left.dts - right.dts);
}

export class Mp4FramePlayer {
    constructor() {
        this.frames = new Map();
        this.samples = [];
        this.presentation = [];
        this.closed = false;
        this.queue = Promise.resolve();
    }

    async load(url) {
        if (!globalThis.VideoDecoder || !globalThis.EncodedVideoChunk) {
            throw new Error('This browser does not support precise MP4 playback. Use a current Chrome or Edge browser.');
        }
        const response = await fetch(url);
        if (!response.ok) throw new Error(`Unable to load analysis MP4 (${response.status}).`);
        const reader = response.body.getReader();
        const chunks = [];
        let size = 0;
        try {
            while (true) {
                const {value, done} = await reader.read();
                if (done) break;
                size += value.byteLength;
                if (size > MAX_ENCODED_BYTES) throw new Error('Analysis MP4 exceeds the 256 MiB playback limit.');
                chunks.push(value);
            }
        } finally {
            await reader.cancel();
        }
        const data = new Uint8Array(size);
        let offset = 0;
        for (const chunk of chunks) { data.set(chunk, offset); offset += chunk.byteLength; }
        const {samples, videoTrack} = await extractMp4Samples(data.buffer);
        if (!samples.length || !samples[0].description.avcC) throw new Error('Analysis MP4 must contain H.264 video.');
        this.samples = samplesInDecodeOrder(samples);
        this.presentation = [...this.samples].sort((a, b) => a.cts - b.cts);
        this.width = videoTrack.video.width;
        this.height = videoTrack.video.height;
        this.fps = videoTrack.nb_samples * videoTrack.timescale / videoTrack.duration;
        const support = await VideoDecoder.isConfigSupported({
            codec: videoTrack.codec, codedWidth: this.width, codedHeight: this.height,
            description: avcDecoderDescription(samples[0].description.avcC),
        });
        if (!support.supported) throw new Error(`Unsupported MP4 decoder: ${videoTrack.codec}`);
        this.config = support.config;
        return this;
    }

    get frameCount() { return this.presentation.length; }

    getFrame(index) {
        const request = this.queue.then(() => this.decodeFrame(index));
        this.queue = request.catch(() => {});
        return request;
    }

    async decodeFrame(index) {
        if (this.closed) throw new Error('Movie player is closed.');
        if (!Number.isInteger(index) || index < 0 || index >= this.frameCount) throw new RangeError('Frame is outside the movie.');
        const sample = this.presentation[index];
        const timestamp = Math.round(sample.cts * MICROSECONDS_PER_SECOND / sample.timescale);
        if (this.frames.has(timestamp)) return this.frames.get(timestamp).clone();
        let start = this.samples.indexOf(sample);
        while (start > 0 && videoFrameType(this.samples[start]) !== 'key') start--;
        let end = start + 1;
        while (end < this.samples.length && videoFrameType(this.samples[end]) !== 'key') end++;
        if (this.width * this.height * 4 * (end - start) > MAX_GROUP_BYTES) {
            throw new Error('MP4 keyframe group exceeds the decoded-frame memory limit.');
        }
        this.clearFrames();
        let decodeError;
        const decoder = new VideoDecoder({
            output: frame => {
                if (this.closed) frame.close();
                else this.frames.set(frame.timestamp, frame);
            },
            error: error => { decodeError = error; },
        });
        try {
            decoder.configure(this.config);
            for (const entry of this.samples.slice(start, end)) {
                decoder.decode(new EncodedVideoChunk({
                    type: videoFrameType(entry),
                    timestamp: Math.round(entry.cts * MICROSECONDS_PER_SECOND / entry.timescale),
                    duration: Math.round(entry.duration * MICROSECONDS_PER_SECOND / entry.timescale),
                    data: entry.data,
                }));
            }
            await decoder.flush();
            if (decodeError) throw decodeError;
            if (this.closed) throw new Error('Movie player is closed.');
            if (!this.frames.has(timestamp)) throw new Error(`Decoder did not produce frame ${index}.`);
            return this.frames.get(timestamp).clone();
        } catch (error) {
            this.clearFrames();
            throw error;
        } finally {
            if (decoder.state !== 'closed') decoder.close();
        }
    }

    clearFrames() {
        for (const frame of this.frames.values()) frame.close();
        this.frames.clear();
    }

    close() {
        this.closed = true;
        this.clearFrames();
        this.samples = [];
        this.presentation = [];
    }
}
