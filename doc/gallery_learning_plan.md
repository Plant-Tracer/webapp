This document describes steps for learning how to use Bottle and Jinja, and then using that knowledge to add a report to the webapp.

# Getting Started

## Read the Docs
Read and be familiar with the documentation for Bottle:

- [ ] Bottle, the framework we are using: https://bottlepy.org/docs/stable/index.html


## Run Bottle Locally
Now that you are familiar with Bottle, see if you can get this tutorial working on your local machine:

- [ ] https://realpython.com/developing-with-bottle-part-1/

## Add the adder application

The current [index.html](https://github.com/Plant-Tracer/webapp/commit/1081873f2fc2af0f623a84777b9646fdcd4b43b8) implements a simple adder that runs in JavaScript. To get the hang of building a web application, your goal is to take your demo program you created above and:

- [ ] Create a new page called `/add.html` that displays the adder HTML
- [ ] Run the demo app and verify that your add.html can be displayed in your web browser.
- [ ] Make a change to add.html and reload the web browser to verify that the change gets made.
- [ ] Create a new page called `/add.js` that serves the JavaScript adder code (currently at https://github.com/Plant-Tracer/webapp/blob/main/static/add_numbers.js)
- [ ] Add the HTML code to `add.html` to load `add.js`
- [ ] Reload, try typing numbers into the two boxes, and verify that you can add them.

# Future work
After you get to this opint, it's time to start thinking about the jinja templating engine


## Understanding Jinja

- [ ] Jinja, the template engine we are using: https://jinja.palletsprojects.com/en/3.1.x/  [Tutorial](https://realpython.com/primer-on-jinja-templating/#render-your-first-jinja-template)

## Setting up Bottle files (route, run, template, static_files)
- setting up HTML (.tpl) https://www.youtube.com/watch?v=Qp-3DBzAEkQ
- routing static files (.css) https://www.youtube.com/watch?v=iLX_iYoNCyU&t=10s

## routing and callback (advanced tutorial)
- https://bottlepy.org/docs/stable/routing.html
