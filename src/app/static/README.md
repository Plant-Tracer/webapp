Do not put binary data in this folder; Lambda cannot serve it.
See https://github.com/Plant-Tracer/webapp/issues/632

``mp4box.all.js`` is the browser ESM build from the exact ``mp4box`` version in
``package-lock.json``. Refresh it from ``node_modules/mp4box/dist/mp4box.all.js``
when that dependency is upgraded, removing trailing whitespace before commit.
