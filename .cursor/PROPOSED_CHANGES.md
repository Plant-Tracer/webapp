# Proposed Changes for Plant Tracer Webapp

This document outlines all proposed changes identified during the codebase review. **None of these changes have been implemented** - they are proposals for review.

## 1. JavaScript Coverage Collection for Pytest/Chromium Tests

### Problem
JavaScript coverage is currently only collected when running Jest unit tests (`npm run coverage`). When JavaScript runs in Chromium via pytest/Selenium tests (e.g., `tests/canvas_movie_controller_test.py`), the coverage is NOT collected. This means we're missing coverage data for JavaScript code that executes in real browser environments.

### Proposed Solution

#### Option A: Use Chrome DevTools Protocol
1. Enable JavaScript coverage collection in Chromium using Chrome DevTools Protocol
2. Inject coverage collection script before page load
3. Extract coverage data after test execution
4. Merge with existing Jest coverage data

**Limitations:**
- Requires Chrome DevTools Protocol support
- Coverage format may differ from Istanbul format used by Jest
- May not capture all code paths accurately
- More complex conversion to merge with Jest coverage

#### Option B: Use babel-plugin-istanbul (Recommended - More Comprehensive)
1. Instrument JavaScript files at build time using `babel-plugin-istanbul`
2. Serve instrumented files in test environment
3. Extract `window.__coverage__` from browser after tests
4. Merge with Jest coverage

**Why Option B is Better:**
- **Same format as Jest**: Uses Istanbul format (`window.__coverage__`), making merging straightforward
- **More comprehensive**: Captures all instrumented code, including dynamically loaded modules
- **Consistent with existing tooling**: Jest already uses Istanbul under the hood
- **Better source map support**: Preserves original source locations accurately
- **Easier integration**: Can reuse existing Jest coverage merging utilities
- **Works with all browsers**: Not limited to Chrome DevTools Protocol

**Implementation Steps for Option B:**
1. Add `babel-plugin-istanbul` to `package.json` devDependencies
2. Configure Babel to use istanbul plugin only in test environment
3. Modify Flask test server to serve instrumented JavaScript files
4. Extract `window.__coverage__` from browser after each test
5. Save coverage data to file in Istanbul format
6. Merge with Jest coverage using existing tools

**Files to Modify:**
- `package.json`: Add `babel-plugin-istanbul` to devDependencies
- `tests/conftest.py`: Add coverage collection to `chrome_driver` fixture, configure instrumented file serving
- `tests/canvas_movie_controller_test.py`: Extract coverage after each test
- `Makefile`: Add script to merge coverage files
- `babel.config.js` or `.babelrc`: Configure istanbul plugin for test environment

**New Files:**
- `tests/js_coverage_utils.py`: Utility functions for collecting/merging coverage

### Benefits
- Complete coverage picture including browser-executed JavaScript
- Better understanding of what code paths are tested in real browser
- Aligns with project goal of comprehensive testing

---

## 2. Test Coverage Improvement Opportunities

### 2.1 Error Handling Paths

**Location**: `src/app/flask_app.py`

**Current Coverage Gap**: Error handlers may not be fully tested
- `handle_exception()` (line 86): Generic exception handler
- `handle_auth_error()` (line 70): AuthError handling
- `handle_apikey_error()` (line 81): InvalidAPI_Key handling

**Proposed Tests:**
- Test unhandled exceptions trigger 500 response
- Test AuthError returns proper JSON response
- Test InvalidAPI_Key returns 403
- Test InvalidUser_Email returns 400

**File**: `tests/flask_error_handling_test.py` (new)

### 2.2 Database Error Scenarios

**Location**: `src/app/odb.py`

**Current Coverage Gap**: Error paths in database operations
- `dynamodb_error_debugger` decorator (line 158): Error handling wrapper
- Connection failures
- Invalid data format handling
- Table health verification (`verify_table_health`, line 704)

**Proposed Tests:**
- Mock DynamoDB errors and verify error handling
- Test `verify_table_health()` with various table states
- Test error decorator behavior

**File**: `tests/odb_error_handling_test.py` (new)

### 2.3 S3 Operations Edge Cases

**Location**: `src/app/s3_presigned.py`

**Current Coverage Gap**: 
- Error handling for S3 operations
- Invalid bucket/key scenarios
- Network failures during presigned URL generation

**Proposed Tests:**
- Test `object_exists()` with various S3 states
- Test presigned URL generation failures
- Test invalid object names

**File**: `tests/s3_error_handling_test.py` (new)

### 2.4 Authentication and Authorization

**Location**: `src/app/auth.py`, `src/app/apikey.py`

**Current Coverage Gap**:
- Expired API keys
- Invalid cookie handling
- Demo mode authentication
- Course admin authorization checks

**Proposed Tests:**
- Test expired API key rejection
- Test invalid cookie formats
- Test demo mode authentication flow
- Test course admin authorization edge cases

**File**: `tests/auth_comprehensive_test.py` (new)

### 2.5 JavaScript Canvas Controller

**Location**: `src/app/static/canvas_controller.mjs`

**Current Coverage Gap**: 
- Error handling in canvas operations
- Edge cases in zoom/pan operations
- Object selection edge cases
- Background image loading failures

**Proposed Tests** (Jest):
- Test error handling when canvas operations fail
- Test zoom limits and edge cases
- Test object selection with overlapping objects
- Test background image loading errors

**File**: `jstests/canvas_controller_error_handling.test.js` (new)

---

## 3. Code Quality Improvements

### 3.1 Typos and Spelling Errors

1. **Makefile line 141**: `covreage` → `coverage`
   ```makefile
   @echo covreage report in htmlcov/
   ```
   Should be: `@echo coverage report in htmlcov/`

2. **lambda-camera/README.md line 33**: `uploade` → `uploaded`
   ```markdown
   - scans for all frames that were uploade
   ```
   Should be: `- scans for all frames that were uploaded`

3. **lambda-camera/README.md line 34**: `create` → `created`
   ```markdown
   - causes a zipfile of all frames to be create and stored.
   ```
   Should be: `- causes a zipfile of all frames to be created and stored.`

4. **README.md line 80**: `Prequisities` → `Prerequisites`
   ```markdown
   Linux and macOS Prequisities
   ```
   Should be: `Linux and macOS Prerequisites`

### 3.2 Code Simplifications

#### 3.2.1 Type Annotations

**Location**: `src/app/flask_app.py`

**Current**: Missing return type annotations
```python
def fix_boto_log_level():
    """Do not run boto loggers at debug level"""
```

**Proposed**:
```python
def fix_boto_log_level() -> None:
    """Do not run boto loggers at debug level"""
```

**Location**: `src/app/flask_app.py` - Error handlers

**Current**: Missing type annotations
```python
@app.errorhandler(404)
def not_found_404(e):
    return f"<h1>404 Not Found (404) </h1><pre>\n{e}\n</pre>", 404
```

**Proposed**:
```python
from flask import Response
from werkzeug.exceptions import NotFound

@app.errorhandler(404)
def not_found_404(e: NotFound) -> tuple[str, int]:
    return f"<h1>404 Not Found (404) </h1><pre>\n{e}\n</pre>", 404
```

#### 3.2.2 Function Signatures in `src/app/odb.py`

Many functions are missing type annotations. Examples:

**Current**:
```python
def new_user_id():
def get_user(user_id):
def create_new_movie(*, user_id, course_id=None, title=None, description=None, orig_movie=None):
```

**Proposed**:
```python
def new_user_id() -> str:
def get_user(user_id: str) -> dict[str, Any] | None:
def create_new_movie(
    *, 
    user_id: str, 
    course_id: str | None = None, 
    title: str | None = None, 
    description: str | None = None, 
    orig_movie: str | None = None
) -> dict[str, Any]:
```

#### 3.2.3 Simplify Error Handler Duplication

**Location**: `src/app/flask_app.py` lines 61-67

**Current**: Two separate 404 handlers doing the same thing
```python
@app.errorhandler(404)
def not_found_404(e):
    return f"<h1>404 Not Found (404) </h1><pre>\n{e}\n</pre>", 404

@app.errorhandler(NotFound)
def not_found_NotFound(e):
    return f"<h1>404 Not Found (NotFound)</h1><pre>\n{e}\n</pre>", 404
```

**Proposed**: Remove duplicate, Flask handles both
```python
@app.errorhandler(NotFound)
def not_found(e: NotFound) -> tuple[str, int]:
    return f"<h1>404 Not Found</h1><pre>\n{e}\n</pre>", 404
```

#### 3.2.4 Simplify Logging Configuration

**Location**: `src/app/flask_app.py` lines 38-42

**Current**: Iterates through all loggers
```python
def fix_boto_log_level():
    """Do not run boto loggers at debug level"""
    for name in logging.root.manager.loggerDict:
        if name.startswith('boto'):
            logging.getLogger(name).setLevel(logging.INFO)
```

**Proposed**: More efficient, set root boto logger
```python
def fix_boto_log_level() -> None:
    """Do not run boto loggers at debug level"""
    logging.getLogger('boto').setLevel(logging.INFO)
    logging.getLogger('boto3').setLevel(logging.INFO)
    logging.getLogger('botocore').setLevel(logging.INFO)
```

### 3.3 Type Annotation Opportunities

#### High Priority (Core Functions)

1. **`src/app/flask_api.py`**: All API endpoint functions
   - Add return type annotations (typically `Response` or `tuple[Response, int]`)
   - Add parameter type annotations

2. **`src/app/odb.py`**: Database operation functions
   - Add return types (most return `dict[str, Any]` or `list[dict[str, Any]]`)
   - Add parameter types for all functions

3. **`src/app/auth.py`**: Authentication functions
   - Add return types
   - Add parameter types

4. **`src/app/s3_presigned.py`**: S3 operation functions
   - Add return types (URLs are `str`, existence checks are `bool`)
   - Add parameter types

#### Medium Priority

5. **`src/app/tracker.py`**: Movie tracking functions
   - Add type annotations for callback functions
   - Add return types

6. **`src/app/mailer.py`**: Email functions
   - Add return types
   - Add parameter types

7. **`src/app/gravitropism.py`**: Calculation functions
   - Add return type annotations (returns `dict[str, float]`)

#### Low Priority (Test Files)

8. **`tests/conftest.py`**: Fixture functions
   - Add return type annotations using `Generator` or `Iterator` types

### 3.4 Code Organization Improvements

#### 3.4.1 Consolidate Constants

**Location**: `src/app/constants.py`

**Current**: Constants scattered across files
- `DEFAULT_OFFSET`, `DEFAULT_SEARCH_ROW_COUNT` in `flask_app.py`
- `MIN_SEND_INTERVAL` in `flask_app.py`
- Various constants in `odb.py`

**Proposed**: Move all constants to `constants.py` for better organization

#### 3.4.2 Remove Unused Code

**Location**: `tests/sitetitle_test.py` line 28

**Current**: Test is skipped with comment "temporarily disabled"
```python
@pytest.mark.skip(reason="temporarily disabled")
def test_sitetitle_just_selenium(http_endpoint):
```

**Proposed**: Either fix and enable, or remove if no longer needed

### 3.5 Documentation Improvements

#### 3.5.1 Add Missing Docstrings

Several functions lack docstrings or have incomplete ones:

- `src/app/flask_app.py`: `fix_boto_log_level()` - could explain why
- `src/app/odb.py`: Many helper functions lack docstrings
- `src/app/gravitropism.py`: `calculate_results_gravitropism()` - could explain formula

#### 3.5.2 Fix Inconsistent Documentation

**Location**: `README.md` line 15

**Current**: Broken link syntax
```markdown
1. A web client written in JavaScript using the JQuery framework. Most of the app is located in (deploy/app/static/)[deploy/app/static/]
```

**Proposed**: Fix markdown link
```markdown
1. A web client written in JavaScript using the JQuery framework. Most of the app is located in [deploy/app/static/](deploy/app/static/)
```

---

## Summary of Proposed Changes

### Priority 1 (Critical)
1. ✅ **Design Document Created** - `.cursor/CURSOR_DESIGN.md`
2. **JavaScript Coverage for Chromium Tests** - Implement Option A (Chrome DevTools Protocol)
3. **Fix Typo**: `covreage` → `coverage` in Makefile

### Priority 2 (Important)
4. **Add Type Annotations** - Core functions in `flask_app.py`, `odb.py`, `flask_api.py`
5. **Test Coverage Improvements** - Error handling paths, edge cases
6. **Fix Remaining Typos** - README, lambda-camera README

### Priority 3 (Nice to Have)
7. **Code Simplifications** - Remove duplicate error handlers, improve logging setup
8. **Documentation** - Add missing docstrings, fix broken links
9. **Code Organization** - Consolidate constants, remove unused code

---

## Implementation Notes

- All changes should maintain backward compatibility
- Type annotations should use Python 3.13+ syntax (`str | None` instead of `Optional[str]`)
- Test coverage improvements should use existing fixtures from `tests/conftest.py`
- JavaScript coverage collection should merge with existing Jest coverage output format

---

## Files That Would Be Modified

### New Files
- `.cursor/CURSOR_DESIGN.md` ✅ (created)
- `.cursor/PROPOSED_CHANGES.md` ✅ (this file)
- `tests/js_coverage_utils.py` (for JavaScript coverage collection)
- `tests/flask_error_handling_test.py`
- `tests/odb_error_handling_test.py`
- `tests/s3_error_handling_test.py`
- `tests/auth_comprehensive_test.py`
- `jstests/canvas_controller_error_handling.test.js`

### Modified Files
- `Makefile` (fix typo, add coverage merging)
- `tests/conftest.py` (add JavaScript coverage collection)
- `tests/canvas_movie_controller_test.py` (extract coverage)
- `src/app/flask_app.py` (type annotations, simplify error handlers)
- `src/app/odb.py` (type annotations)
- `src/app/flask_api.py` (type annotations)
- `src/app/auth.py` (type annotations)
- `src/app/s3_presigned.py` (type annotations)
- `README.md` (fix typos and links)
- `lambda-camera/README.md` (fix typos)
- `package.json` (potentially add babel-plugin-istanbul if using Option B)

