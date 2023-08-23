MOVIE = "data/2019-07-31 plantmovie.mov"
extract_and_upload:
	TMP=`mktemp -d` ; ffmpeg -i $(MOVIE) $$TMP/frame_%04d.jpg ; echo $$TMP ; ls -l $$TMP

pytest:
	cd ..;make pytest
