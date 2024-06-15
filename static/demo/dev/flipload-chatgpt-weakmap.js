const imageCache = new WeakMap();
const imageAccess = new Map(); // Holds strong references based on usage logic

// Function to load an image with retries
function loadImage(url, maxRetries, retryInterval) {
    let img = new Image();
    let retries = 0;

    function attemptLoad() {
        img.src = "";  // Clear the source to ensure the browser attempts a reload
        img.src = url;
    }

    img.onload = () => {
        console.log(`Image loaded successfully: ${url}`);
        // Add to WeakMap for weak reference caching
        imageCache.set(img, url);
        // Add to Map for strong reference based on access
        imageAccess.set(url, img);
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

// Function to access an image
function getImage(url, maxRetries = 3, retryInterval = 2000) {
    let img = imageAccess.get(url);
    if (!img) {
        // Not in the strong map, check weak map or reload
        img = imageCache.get(img);
        if (!img) {
            // Not in cache or garbage collected, reload
            img = loadImage(url, maxRetries, retryInterval);
        } else {
            // Update strong reference as it's being accessed
            imageAccess.set(url, img);
        }
    }
    return img;
}

// Example usage:
const urls = ["http://company.com/image1.png", "http://company.com/image2.png", /* up to 500 URLs */];
urls.forEach(url => getImage(url));
