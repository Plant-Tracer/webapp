# Copilot Instructions for Plant-Tracer Webapp

## Database Access (ODB Module)

### Important: Always Use Correct ODB Method Patterns

When working with the `app.odb` module, follow these patterns:

1. **Module-level functions** are available directly via `odb.<function>()`:
   - `odb.get_movie(movie_id=movie_id)`
   - `odb.get_movie_trackpoints(movie_id=movie_id, frame_start=0, frame_count=1)`
   - `odb.get_movie_metadata(movie_id=movie_id)`
   - `odb.put_frame_trackpoints(movie_id=movie_id, frame_number=0, trackpoints=[])`

2. **Instance methods** require creating a `DDBO()` instance first:
   ```python
   from app.odb import DDBO

   ddbo = DDBO()  # It's a singleton
   api_key_dict = ddbo.get_api_key_dict(api_key)
   movie_dict = ddbo.get_movie(movie_id)
   ```

3. **Before using any ODB method:**
   - Check `src/app/odb.py` to verify the method exists
   - Confirm whether it's a module-level function or instance method
   - Check the method signature and required parameters

### Common Mistake to Avoid

❌ **WRONG:** `odb.get_api_key_dict(api_key)`
- This will cause `AttributeError: module 'app.odb' has no attribute 'get_api_key_dict'`

✅ **CORRECT:**
```python
from app.odb import DDBO
ddbo = DDBO()
api_key_dict = ddbo.get_api_key_dict(api_key)
```

### How to Verify

Before using any ODB method in your code:

```bash
# Search for the method definition
grep -n "def method_name" src/app/odb.py

# Check if it's at module level or in the DDBO class
grep -B 5 "def method_name" src/app/odb.py
```

## Testing Best Practices

### Fixtures

See `FIXTURES_REFERENCE.md` for details on available test fixtures and what they provide.

### Authentication

Always use cookie-based authentication in Selenium tests, not URL parameters:

```python
# Set cookie before navigating to authenticated pages
chrome_driver.get(live_server)
chrome_driver.add_cookie({
    'name': 'api_key',
    'value': api_key,
    'path': '/'
})
# Now navigate to authenticated pages
chrome_driver.get(f"{live_server}/list")
```
