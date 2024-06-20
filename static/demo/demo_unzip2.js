/*jslint browser */

import { CanvasController, CanvasItem, Marker, WebImage } from "../canvas_controller.js";
import { MovieController } from "../canvas_movie_controller.js";
import {unzip, setOptions} from '../unzipit.module.js';

setOptions({
  workerURL: '../unzipit-worker.module.js',
  numWorkers: 2,
});


async function onload(e) {
    console.log("onload");
    const frames = [];

    const {entries} = await unzip('./tracked.zip');
    const names = Object.keys(entries).filter(name => name.endsWith('.jpg'));
    const blobs = await Promise.all(names.map(name => entries[name].blob()));
    names.forEach((name, i) => {
        console.log("name=",name,"i=",i);
        frames[i] = {'frame_url':URL.createObjectURL(blobs[i])};
    });
    const cc = new MovieController('div#movie_controller');
    cc.load_movie(frames);
    cc.set_loop(true);
}

addEventListener("load", onload);
