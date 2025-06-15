#!/usr/bin/env bash
set -e
#
# Run or Stop DynamoDBLocal on both Linux and MacOS
# Assumes DynamoDB installed in the root directory

export MINIO_ROOT_USER=minioadmin
export MINIO_ROOT_PASSWORD=minioadmin
export MINIO_API_CORS_ALLOW_ORIGIN="*"
MYDIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LOGDIR="$(dirname $MYDIR)/logs"
DBDIR="$(dirname $MYDIR)/var"
FLAGS="--address 127.0.0.1:9000 --console-address 127.0.0.1:9001 "
MINIO=$MYDIR/minio
PIDFILE="$DBDIR/minio.pid"

command -v pgrep > /dev/null || {
    echo "Error: pgrep is required but not found."
    exit 1
}

wait_minio() {
    # Wait for port 9000 to be accepting connections
    for i in {1..15}; do
        if curl -s http://localhost:9000/ > /dev/null; then
            echo "Minio is ready."
            break
        fi
        echo "  Waiting for Minio to be ready ($i)..."
        sleep 1
    done
}

# Function to start Minio
start_minio() {
    # Check if MinioLocal is already running
    if pgrep -f "minio" > /dev/null
    then
        wait_minio
        echo "minio is already running."
        exit 0
    fi

    # Run Minio Local in the background, redirecting output
    if [ ! -d $DBDIR ]; then
        echo creating $DBDIR
        mkdir -p $DBDIR
    fi
    echo "Starting Minio ..."
    $MINIO server $FLAGS $DBDIR > "$LOGDIR/minio.stdout" 2> "$LOGDIR/minio.stderr" &
    echo $! > $PIDFILE # Store the PID in a file

    echo "Minio Local started in the background (PID: $!)."
    wait_minio

}

# Function to stop Minio Local
stop_minio() {
    if [ -f $PIDFILE ]; then
        PID=$(cat $PIDFILE)
        if ps -p $PID > /dev/null; then
            echo "Stopping Minio Local (PID: $PID)..."
            kill $PID
            # Give it a moment to shut down gracefully
            sleep 2
            if ps -p $PID > /dev/null; then
                echo "Minio Local (PID: $PID) did not shut down gracefully. Forcing kill."
                kill -9 $PID  # Force kill if it's still running
            fi
            rm -f $PIDFILE
            echo "Minio Local stopped."
        else
            echo "PID file exists but Minio Local (PID: $PID) is not running. Removing stale PID file."
            rm -f $PIDFILE
        fi
    else
        echo "No $PIDFILE file found. Checking for running process with pgrep."
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
    "") set -- status
        ;;

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
    debug)
        echo MYDIR=$MYDIR
        echo LOGDIR=$LOGDIR
        echo DBDIR=$DBDIR
        echo FLAGS=$FLAGS
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac

exit 0
