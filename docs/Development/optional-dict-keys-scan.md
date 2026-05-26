# Optional / possibly-missing dict keys – codebase scan

Scanned for `obj[key]`-style access where the key might be missing (potential `KeyError`). Grouped by category. Use `.get(key, default)` or check `key in obj` before subscript when the key is optional.

---

## Category 1: Movie dict – keys that may be absent

**Source:** `get_movie()` / `get_movie_metadata()` / DynamoDB movies table. Movies can be in different states (just created, uploading, processing, zip not built yet, etc.).

| Location | Key | Risk | Notes |
|----------|-----|------|--------|
| `odb.py` ~1486 | `LAST_FRAME_TRACKED` | **FIXED** | Now uses `.get(LAST_FRAME_TRACKED, None)`. |
| `odb.py` 1356 | `COURSE_ID` | Low | Set at movie create; could be missing only if DB is inconsistent. |
| `odb.py` 1361 | `MOVIE_DATA_URN` | **FIXED** | `movie_data_urn_for_movie_id()` now uses `.get(MOVIE_DATA_URN)`. |
| `odb.py` 1367 | `MOVIE_ZIPFILE_URN` | **FIXED** | `movie_zipfile_urn_for_movie_id()` now uses `.get(MOVIE_ZIPFILE_URN)`. |
| `odb_movie_data.py` 108–110 | `MOVIE_ZIPFILE_URN`, `MOVIE_DATA_URN` | **FIXED** | `get_movie_data()` uses `.get()`; no try/except needed. |
| `odb_movie_data.py` 131, 145 | `VERSION` | **FIXED** | `set_movie_data()` uses `movie.get(VERSION, 0)`. |
| `odb_movie_data.py` 186 | `MOVIE_ZIPFILE_URN` | **FIXED** | `purge_movie_zipfile()` uses `urn = movie.get(...)` then `delete_object(urn)`. |
| `flask_api.py` 449 | `MOVIE_ZIPFILE_URN` | Medium | After `if movie_metadata.get(MOVIE_ZIPFILE_URN, None)`; then we do `movie_metadata[MOVIE_ZIPFILE_URN]` – safe if logic is correct. |

**Recommendations:** All high-priority movie URN/version fixes above are implemented.

---

## Category 2: User dict – keys that may be absent

**Source:** `get_user()` / DynamoDB users table. Some attributes are set only when the user is an admin or has a primary course.

| Location | Key | Risk | Notes |
|----------|-----|------|--------|
| `flask_api.py` 314 | `'primary_course_id'` | **High** | New user or user without primary course → KeyError when creating a movie. |
| `odb.py` 1268 | `PRIMARY_COURSE_ID` | **High** | `course_id = user[PRIMARY_COURSE_ID]` in `list_movies`; can be missing. |
| `apikey.py` 176 | `'primary_course_id'` | Medium | `user_dict['primary_course_id']`; may be None for some users (apikey sets it to None in one branch). |
| `odb.py` 517, 618, 959, 966, 992, 1002, 1104–1105, 1130, 1172, 1245, 1343, 1576–1577, 1593 | `COURSES`, `ADMIN_FOR_COURSES`, `USER_ID`, etc. | Low–Medium | Schema and add-course logic usually set these; missing only on legacy or partial records. |

**Recommendations:**

- `flask_api.api_new_movie`: use `user.get('primary_course_id')` (or `PRIMARY_COURSE_ID`) and return 400 if missing (e.g. “Set a primary course before creating a movie”).
- `odb.list_movies`: use `user.get(PRIMARY_COURSE_ID)` and handle None (e.g. no movies for that user, or fetch by another rule).
- `apikey.py`: use `user_dict.get('primary_course_id')` and handle None where needed.

---

## Category 3: Course dict – keys from DynamoDB

**Source:** `get_course()` / DynamoDB courses table. Schema defines expected attributes.

| Location | Key | Risk | Notes |
|----------|-----|------|--------|
| `odb.py` (multiple) | `COURSE_ID`, `COURSE_NAME`, `ADMINS_FOR_COURSE` | Low | Part of core course schema; only risky if table is corrupted or schema changed. |

No change suggested unless you add stricter typing (e.g. TypedDict).

---

## Category 4: DynamoDB / boto3 response shapes

**Source:** `response` from `query()`, `scan()`, `get_item()`, etc.

| Location | Key | Risk | Notes |
|----------|-----|------|--------|
| `odb.py` 845 | `response['LastEvaluatedKey']` | Low | Only used when `'LastEvaluatedKey' in response` (line 843). |
| Various | `response['Items']` | Low | Standard DynamoDB contract; use `response.get('Items', [])` if you want to be defensive. |
| Various | `e.response['Error']['Code']` | Low | boto3 ClientError contract; documented structure. |

Optional hardening: use `response.get('Items', [])` and `response.get('LastEvaluatedKey')` where pagination is used.

---

## Category 5: Item/frame from query or batch

**Source:** Items from `response['Items']`, or from `get_movie_frame()`, etc.

| Location | Key | Risk | Notes |
|----------|-----|------|--------|
| `odb.py` 734–735 | `movie_frame[MOVIE_ID]`, `movie_frame[FRAME_NUMBER]` | Low | From movie_frames table; primary key attributes. |
| `odb.py` 1424, 1435–1437 | `frame[FRAME_NUMBER]`, `frame[MOVIE_ID]`, `frame[FRAME_URN]` | Low | Same table, expected attributes. |
| `odb.py` 506, 1201 | `item[API_KEY]`, `item[USER_ID]` | Low | From api_keys / users tables; key attributes. |

Generally safe; only change if you add optional attributes to those tables.

---

## Category 6: Newly created / in-memory dicts

**Source:** `ret = {'error': False}`, `create_new_movie` return value, etc.

| Location | Key | Risk | Notes |
|----------|-----|------|--------|
| `flask_api.py` 313–328 | `ret[MOVIE_ID]`, `user['primary_course_id']` | **High** (user) | `ret` is built in this function; `user` is from `get_user()` – use `.get('primary_course_id')` as above. |

---

## Summary – high‑value fixes

1. **Movie (done):** `movie_data_urn_for_movie_id`, `movie_zipfile_urn_for_movie_id`, `get_movie_data`, `set_movie_data`, `purge_movie_zipfile`, and Lambda `lambda_tracking_env.get_movie_data` now use `.get()` for URNs and `VERSION`.
2. **User (pending):** `flask_api` new-movie path – use `user.get('primary_course_id')` and handle None.
3. **User (pending):** `odb.list_movies` – use `user.get(PRIMARY_COURSE_ID)` and handle None.
4. **User (pending):** `apikey` – use `user_dict.get('primary_course_id')` where appropriate.

Optional: add a TypedDict (or similar) for movie/user so Pyright can warn on missing optional keys when you use `[]` instead of `.get()`.

---

## Pydantic types for User and Movie – scope evaluation

**Current state:** `schema.py` already defines Pydantic `User` and `Movie` models. They are used for **validation on write** (`put_user`, `put_movie` use `User(**user)` / `Movie(**moviedict)`). `get_user` and `get_movie` return **plain dicts** (DynamoDB items, with `fix_movie()` applied for movies in some code paths).

**What “moving to Pydantic” would mean:** Have `get_user()` and `get_movie()` return `User` and `Movie` instances instead of dicts, and type hints accordingly. That would give attribute access, optional-field safety, and better static checking.

### Extent of change

| Area | Effort | Notes |
|------|--------|--------|
| **Return type of get_movie / get_user** | Small | In `odb.py`, have `get_movie` return `Movie(**fix_movie(item))` and `get_user` return `User(**fix_user(item))` (see below). Handle `ValidationError` for bad DB data (log and re-raise or return None per policy). |
| **fix_user** | Small | There is `fix_movie` / `fix_movie_prop_value` for DynamoDB→Python types (Decimal→int, etc.). You’d add a similar `fix_user` (and possibly `fix_course`) so DynamoDB output fits the Pydantic model. |
| **Call sites using dict subscript** | None | Pydantic `BaseModel` supports `obj['key']` via `__getitem__`, so existing `movie[MOVIE_ID]`, `user[USER_ID]` etc. keep working. |
| **Call sites using .get()** | **Medium** | Models don’t have `.get(key, default)`. There are ~15+ places that do `movie.get(...)` or `user.get(...)` (in `odb.py`, `odb_movie_data.py`, `resize.py`, `lambda_tracking_env.py`, `flask_api.py`, etc.). Each would need to become `getattr(obj, attr, default)` or a small helper (e.g. `get_model_attr(m, KEY, default)`), or you keep a `.get()`-like method on the model (e.g. a custom method or `model_dump().get()`). |
| **Lambda / vendored app** | Medium | Same `.get()` and type changes in `lambda-resize` and any vendored copies of app code. |
| **Tests** | Low–medium | Tests that build dicts and pass to code expecting User/Movie may need to use `User(...)` / `Movie(...)` or `.model_dump()` where a dict is required. |
| **Schema optionality** | Small | `User` currently has `primary_course_id: str`. For legacy users or “no course yet”, that would need to be `str \| None` and call sites that assume “always set” would need to handle None (as in the Category 2 fixes). |

### Recommendation

- **Short term:** Keep returning dicts from `get_movie`/`get_user`; keep validating on write with existing Pydantic models. The optional-key fixes (e.g. `.get()` for `primary_course_id`, URNs, version) are the main win and are done or documented.
- **If you move to Pydantic return types:**
  1. Add `fix_user()` (and optionally `fix_course()`) for DynamoDB payloads.
  2. Change `get_movie`/`get_user` to return `Movie`/`User`, with `ValidationError` handling.
  3. Replace every `movie.get(KEY, default)` / `user.get(KEY, default)` with a single pattern: e.g. `getattr(m, KEY, default)` or a helper so Pyright and readers see one convention. Expect on the order of **20–30 call sites** across app and lambda.
  4. Make `User.primary_course_id` optional (`str \| None`) if that reflects real data; then handle None in the few places that use it.

Overall: **moderate** effort (roughly half a day to a day of focused refactor plus tests), with the main cost being the `.get()` call sites and keeping lambda/vendored code in sync.
