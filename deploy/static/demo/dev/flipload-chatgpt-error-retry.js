// Function to load an image with retries
function loadImage(url, maxRetries, retryInterval) {
    const img = new Image();
    let retries = 0;

    // Function to attempt loading the image
    function attemptLoad() {
        img.src = "";  // Clear the source to ensure the browser attempts a reload
        img.src = url;
    }

    img.onload = () => {
        console.log(`Image loaded successfully: ${url}`);
    };

    img.onerror = () => {
        if (retries < maxRetries) {
            retries++;
            console.log(`Loading failed for ${url}, retrying... (${retries})`);
            setTimeout(attemptLoad, retryInterval);
        } else {
            console.error(`Failed to load image after ${maxRetries} attempts: ${url}`);
        }
    };

    attemptLoad();
    return img;
}

// Example usage: Load an array of images
const urls = ["http://company.com/image1.png", "http://company.com/image2.png", /* up to 500 URLs */];
const images = urls.map(url => loadImage(url, 3, 2000));  // max 3 retries, 2000 ms between retries
