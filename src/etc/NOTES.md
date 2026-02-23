ffmpeg static binaries (for environments without system ffmpeg, e.g. Lambda):
- src/etc/ffmpeg-6.1-amd64-static (x86_64)
- src/etc/ffmpeg-6.1-arm64-static (aarch64/arm64)
Do not fetch from external sites. Obtain from a trusted source or build from source; store in repo via LFS if needed. On VMs, the app prefers system ffmpeg (/usr/bin/ffmpeg, etc.) when present. For Lambda: if a function needs ffmpeg, bundle only the static binary matching that function's architecture (e.g. arm64 for current lambda-resize template); lambda-resize itself uses PyAV only and does not ship ffmpeg.

add database comments for each table.

- primary_course_id remembers current course.  -> default_course_id



- upload page should set cookie
- list page should set cooike

course edit page:
- Shows students enrolled
- Shows the key
- Shows enrollments left
- Allows changing the key
- Shown to all users who are admins for that course.


- Need to create superadmin
- Can create new courses
- Add admin capabilities to an existing user.

table to implement
- Log table


movie data:
+ Have URL for a movie instead of blob..
+ Movie_data

movies table - add more fields:
- Version Number
- Derrived from
- Processed
- Processor


analysis:
movie_analysis
- Movie_id -
- analysis_engine id
- JSON

movie_frame_analysis
- Movie_id
- movie_frame_id
- analysis_engine id
- JSON

engine table:
id -
engine_name - name
