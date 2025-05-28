#!/bin/bash -e
#
# Run or Stop DynamoDBLocal on both Linux and MacOS
# Assumes DynamoDB installed in the root directory

OPTIONS="-sharedDb -dbPath db -port 8010"

# Function to start DynamoDB Local
start_dynamodb_local() {
    # Check if DynamoDBLocal is already running
    if pgrep -f "DynamoDBLocal.jar" > /dev/null
    then
        echo "DynamoDB Local is already running."
        exit 0
    fi

    # Set JAVA_HOME dynamically for macOS using Homebrew
    if [ "$(uname -s)" = 'Darwin' ]; then
        export JAVA_HOME="$(brew --prefix openjdk)"
        export PATH="$JAVA_HOME/bin:$PATH"
    fi

    # Run DynamoDB Local in the background, redirecting output
    echo "Starting DynamoDB Local..."
    java -Djava.library.path=./DynamoDBLocal_lib -jar DynamoDBLocal.jar $OPTIONS > dynamodb_local.stdout 2> dynamodb_local.stderr &
    echo $! > dynamodb_local.pid # Store the PID in a file

    echo "DynamoDB Local started in the background (PID: $!)."
    echo "Check dynamodb_local.stdout and dynamodb_local.stderr for output."
}

# Function to stop DynamoDB Local
stop_dynamodb_local() {
    if [ -f dynamodb_local.pid ]; then
        PID=$(cat dynamodb_local.pid)
        if ps -p $PID > /dev/null; then
            echo "Stopping DynamoDB Local (PID: $PID)..."
            kill $PID
            # Give it a moment to shut down gracefully
            sleep 2
            if ps -p $PID > /dev/null; then
                echo "DynamoDB Local (PID: $PID) did not shut down gracefully. Forcing kill."
                kill -9 $PID # Force kill if it's still running
            fi
            rm dynamodb_local.pid
            echo "DynamoDB Local stopped."
        else
            echo "PID file exists but DynamoDB Local (PID: $PID) is not running. Removing stale PID file."
            rm dynamodb_local.pid
        fi
    else
        echo "No dynamodb_local.pid file found. Checking for running process with pgrep."
        PID=$(pgrep -f "DynamoDBLocal.jar")
        if [ -n "$PID" ]; then
            echo "Found running DynamoDB Local (PID: $PID) using pgrep. Stopping..."
            kill $PID
            sleep 2
            if ps -p $PID > /dev/null; then
                echo "DynamoDB Local (PID: $PID) did not shut down gracefully. Forcing kill."
                kill -9 $PID
            fi
            echo "DynamoDB Local stopped."
        else
            echo "DynamoDB Local is not running."
        fi
    fi
}

# Main script logic
case "$1" in
    start)
        start_dynamodb_local
        ;;
    stop)
        stop_dynamodb_local
        ;;
    restart)
        stop_dynamodb_local
        start_dynamodb_local
        ;;
    status)
        if pgrep -f "DynamoDBLocal.jar" > /dev/null
        then
            echo "DynamoDB Local is running."
        else
            echo "DynamoDB Local is not running."
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac

exit 0
