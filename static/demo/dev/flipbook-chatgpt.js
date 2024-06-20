// Set up the canvas
const canvas = document.createElement('canvas');
canvas.width = 800;  // Adjust to fit your image dimensions
canvas.height = 600; // Adjust to fit your image dimensions
document.body.appendChild(canvas);
const context = canvas.getContext('2d');

// Create two Image objects and load the images
const imageA = new Image();
const imageB = new Image();
imageA.src = 'http://company.com/one.png';
imageB.src = 'http://company.com/two.png';

// Variables to keep track of the current image
let currentImage = 'A';

// Function to toggle between the images
function toggleImage() {
    if (currentImage === 'A') {
        context.drawImage(imageA, 0, 0, canvas.width, canvas.height);
        currentImage = 'B';
    } else {
        context.drawImage(imageB, 0, 0, canvas.width, canvas.height);
        currentImage = 'A';
    }
}

// Set an interval to toggle the images every 10 seconds
setInterval(toggleImage, 10000);

// Initialize by drawing the first image
imageA.onload = () => context.drawImage(imageA, 0, 0, canvas.width, canvas.height);
