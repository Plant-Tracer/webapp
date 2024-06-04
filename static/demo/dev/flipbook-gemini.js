<canvas id="imageCanvas"></canvas>
<script>
  const canvas = document.getElementById('imageCanvas');
  const ctx = canvas.getContext('2d');
  let currentImage = 0; // Keeps track of current image (0 or 1)
  const images = [
    'http://company.com/one.png',
    'http://company.com/two.png'
  ];

  function loadImage(imageUrl) {
    return fetch(imageUrl)
      .then(response => response.blob())
      .then(blob => URL.createObjectURL(blob));
  }

  async function updateImage() {
    const imageUrl = images[currentImage];
    const imageSrc = await loadImage(imageUrl);
    const image = new Image();
    image.onload = function() {
      canvas.width = image.width;
      canvas.height = image.height;
      ctx.drawImage(image, 0, 0);
    };
    image.src = imageSrc;
    currentImage = (currentImage + 1) % images.length; // Toggle between images
  }

  updateImage(); // Load initial image
  setInterval(updateImage, 10000); // Update image every 10 seconds
</script>
