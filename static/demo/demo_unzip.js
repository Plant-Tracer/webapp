import {unzip, setOptions} from '../unzipit.module.js';

setOptions({
  workerURL: '../unzipit-worker.module.js',
  numWorkers: 2,
});


(async function() {

	const {entries} = await unzip('./tracked.zip');
  const names = Object.keys(entries).filter(name => name.endsWith('.jpg'));
  const blobs = await Promise.all(names.map(name => entries[name].blob()));
  names.forEach((name, i) => {
    console.log("name=",name,"i=",i);
    const img = new Image();
    img.title = name;
    img.src = URL.createObjectURL(blobs[i]);
    document.body.appendChild(img);
  });

}());
