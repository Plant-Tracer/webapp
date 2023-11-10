# pylint: disable=no-member
import cv2
import numpy as np
import json
import argparse

def track_movie(movie, apex_points):
    """
    Summary - takes in a movie(cap) and returns annotatted movie
    takes a annotated frame (marked_frame) that has the apex annotated
    takes the control points (apex_points) 
    initializes parameters to pass to track_frame
    returns a list of points
    
    """
    video_coordinates = np.array(apex_points)
    p0 = apex_points
    cap = cv2.VideoCapture(movie)
    ret, current_frame = cap.read()

    # should be movie name + tracked
    output_video_path = 'tracked_movie.mp4'

    # Get video properties
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    # Create a VideoWriter object to save the output video
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_video_path, fourcc, fps, (width, height))

    # mark the current_frame with the initial apex_points
    for point in apex_points:
        x, y = point.ravel()
        tracked_current_frame = cv2.circle(current_frame, (int(x), int(y)), 3, (0, 0, 255), -1)
        out.write(tracked_current_frame)

    while ret:
        prev_frame = current_frame
        ret, current_frame = cap.read()
        if not ret:
            break

        p0, status, err = track_frame(prev_frame, current_frame, p0) #, winSize=(15, 15), maxLevel=2, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03))
        video_coordinates = p0.tolist()
        
        # use the points to annotate the colored frames. write to colored tracked video
        for point in p0:
            x, y = point.ravel()
            tracked_current_frame = cv2.circle(current_frame, (int(x), int(y)), 3, (0, 0, 255), -1)# pylint: disable=no-member
            # Save the frame to the output video
            out.write(tracked_current_frame)

    cap.release()
    out.release()  
    return video_coordinates    


def track_frame(prev_frame, current_frame, p0):
    """
    Summary - Takes the original marked marked_frame and new frame and returns a frame that is annotated.
    takes a
    returns the new positions.
    
    """
    winSize=(15, 15)
    maxLevel=2
    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)

    gray_prev_frame = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    gray_current_frame = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
    p1, status, err = cv2.calcOpticalFlowPyrLK(gray_prev_frame, gray_current_frame, p0, None, winSize=winSize, maxLevel=maxLevel, criteria=criteria)

    return p1, status, err

if __name__ == "__main__":

    # the only requirement for calling track_movie() would be the "control points" and the movie
    
    
    parser = argparse.ArgumentParser(description="Run Track movie with specified movies and initial points",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    parser.add_argument(
        "--moviefile", default='tests/data/2019-07-12 circumnutation.mp4', help='mpeg4 file')
    parser.add_argument(
        "--points_to_track", default='[[279, 223]]', help="list of points to track as json 2D array.")
    args = parser.parse_args()
    apex_points = np.array(json.loads(args.points_to_track), dtype=np.float32)
    track_movie(args.moviefile, apex_points)