#!/bin/bash -e
#
# Run or Stop DynamoDBLocal on both Linux and MacOS
# Assumes DynamoDB installed in the root directory

export MINIO_ROOT_USER=admin
export MINIO_ROOT_PASSWORD=password
DB="$HOME/s3"
FLAGS="$DB --console-address :9001"
MINIO=./minio

# Function to start Minio
start_minio() {
    # Check if MinioLocal is already running
    if pgrep -f "minio" > /dev/null
    then
        echo "minio is already running."
        exit 0
    fi

    # Run Minio Local in the background, redirecting output
    if [ ! -d $DB ]; then
      echo creating $DB
      mkdir -p $DB
    fi
    echo "Starting Minio ..."
    $MINIO server $FLAGS > minio.stdout 2> minio.stderr &
    echo $! > minio.pid # Store the PID in a file

    echo "Minio Local started in the background (PID: $!)."
    echo "Check minio.stdout and minio.stderr for output."
}

# Function to stop Minio Local
stop_minio() {
    if [ -f minio.pid ]; then
        PID=$(cat minio.pid)
        if ps -p $PID > /dev/null; then
            echo "Stopping Minio Local (PID: $PID)..."
            kill $PID
            # Give it a moment to shut down gracefully
            sleep 2
            if ps -p $PID > /dev/null; then
                echo "Minio Local (PID: $PID) did not shut down gracefully. Forcing kill."
                kill -9 $PID  # Force kill if it's still running
            fi
            rm minio.pid
            echo "Minio Local stopped."
        else
            echo "PID file exists but Minio Local (PID: $PID) is not running. Removing stale PID file."
            rm minio.pid
        fi
    else
        echo "No minio.pid file found. Checking for running process with pgrep."
        PID=$(pgrep -f "minio")
        if [ -n "$PID" ]; then
            echo "Found running Minio Local (PID: $PID) using pgrep. Stopping..."
            kill $PID
            sleep 2
            if ps -p $PID > /dev/null; then
                echo "Minio (PID: $PID) did not shut down gracefully. Forcing kill."
                kill -9 $PID
            fi
            echo "Minio stopped."
        else
            echo "Minio is not running."
        fi
    fi
}

# Main script logic
case "$1" in
    start)
        start_minio
        ;;
    stop)
        stop_minio
        ;;
    restart)
        stop_minio
        start_minio
        ;;
    status)
        if pgrep -f "minio" > /dev/null
        then
            echo "Minio is running."
        else
            echo "Minio is not running."
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac

exit 0
