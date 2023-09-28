MOVIE = "data/2019-07-31 plantmovie.mov"
extract_and_upload:
	TMP=`mktemp -d` ; ffmpeg -i $(MOVIE) $$TMP/frame_%04d.jpg ; echo $$TMP ; ls -l $$TMP

# https://stackoverflow.com/questions/14405063/how-to-see-normal-print-output-created-during-pytest-run
bt:
	cd ..;python -m pytest tests/tracker_test.py -k test_blocktrack -v --log-cli-level=DEBUG

pytest:
	python -m pytest -v --log-cli-level=DEBUG
