const { test, expect } = require('@playwright/test');

test('should detect and fail on console errors', async ({ page }) => {
  let hasConsoleError = false;


  // Navigate to your project
  await page.goto('http://localhost:8080'); 
  await page.waitForLoadState('load');

  // Listen for console messages
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      const text = msg.text();

      // Ignore 403 Forbidden errors
      if (text.includes('Failed to load resource') && text.includes('403')) {
        console.warn(`Ignored 403 error: ${text}`);
      } else {
        console.error(`Console error detected: ${text}`);
        hasConsoleError = true; // Set error flag
      }
    }
  });

  // Check for any console errors
  expect(hasConsoleError).toBe(false); // Fail the test if there were console errors
});
