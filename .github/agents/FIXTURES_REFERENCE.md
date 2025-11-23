# Test Fixtures Reference

This document describes the test fixtures available in the webapp repository to help prevent common mistakes when writing tests.

## Authentication and API Keys

**IMPORTANT**: Most pages in the webapp require authentication via an `api_key`. When testing with Selenium/browser tests, always pass the `api_key` as a URL parameter or set it as a cookie.

Example:
```python
url = f"{live_server}/list?api_key={api_key}"
chrome_driver.get(url)
```

## Available Fixtures

### `new_movie` fixture provides
- **MOVIE_ID**: The created movie's ID
- **API_KEY**: API key for authentication (REQUIRED for authenticated pages like /list)
- **ADMIN_ID**: Admin user ID (movie owner)
- **USER_ID**: Regular user ID
- **COURSE_ID**, **COURSE_NAME**: Course information
- **MOVIE_TITLE**: The movie's title

**CRITICAL**: Always pass `api_key` as URL parameter for authenticated pages:
```python
url = f"{live_server}/list?api_key={new_movie[API_KEY]}"
```

## Common Mistake: Missing API Key

❌ **WRONG** - This will fail with "Page has 67 chars":
```python
url = f"{live_server}/list"
chrome_driver.get(url)
```

✅ **CORRECT** - Always include api_key:
```python
api_key = new_movie[API_KEY]
url = f"{live_server}/list?api_key={api_key}"
chrome_driver.get(url)
```
