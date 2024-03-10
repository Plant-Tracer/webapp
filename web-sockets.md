Below is an example of how you can achieve this with JavaScript on the client-side and Python with Bottle on the server-side.

**Client-side JavaScript:**
```javascript
<script>
  // Function to handle receiving lines from server
  function receiveLine(line) {
    console.log(line);
  }

  // Function to establish WebSocket connection and handle received messages
  function connectWebSocket() {
    const socket = new WebSocket('ws://localhost:8080/ws');

    socket.onopen = function(event) {
      console.log('WebSocket connection established');
    };

    socket.onmessage = function(event) {
      receiveLine(event.data);
    };

    socket.onclose = function(event) {
      console.log('WebSocket connection closed');
    };
  }

  // Call the connectWebSocket function when the page loads
  window.onload = function() {
    connectWebSocket();
  };
</script>
```

**Python Bottle Server:**
```python
from bottle import route, run, static_file, template
import time
from threading import Thread
import websocket

@route('/ws')
def handle_websocket():
    ws = websocket.websocket(request.environ.get('wsgi.websocket'))
    for i in range(1, 101):
        time.sleep(1)  # 1 second pause
        ws.send("This is line {}".format(i))
    ws.close()

@route('/')
def index():
    return static_file('index.html', root='.')

if __name__ == '__main__':
    # Start WebSocket server in a separate thread
    websocket_thread = Thread(target=run, kwargs={'server': 'gevent', 'host': 'localhost', 'port': 8080})
    websocket_thread.start()

    # Start Bottle server for serving static files
    run(host='localhost', port=8000)
```

WebSockets are built on top of TCP (Transmission Control Protocol) connections but they are not the same as regular sockets. While regular sockets allow for bidirectional communication over a network, they lack the features that make WebSockets particularly suitable for web-based applications.

Here are some key differences between WebSockets and regular sockets:

1. **HTTP-Based Handshake**: WebSockets start with an HTTP-based handshake, which allows them to traverse proxies and firewalls more easily compared to raw sockets.

2. **Full-Duplex Communication**: WebSockets support full-duplex communication, meaning both the client and server can send messages to each other simultaneously without waiting for a response. This is different from typical HTTP request-response cycles.

3. **Message Framing**: WebSockets add a framing layer on top of the TCP connection. This framing layer enables the sending and receiving of messages as discrete units, rather than streams of bytes, making it easier to manage message boundaries.

4. **Higher-Level Protocol**: WebSockets define a higher-level protocol that allows for more efficient and structured communication. For example, they support text and binary message types, as well as ping/pong messages for heartbeat and connection keep-alive.

5. **WebSocket API**: WebSockets are typically accessed through an API provided by web browsers or WebSocket libraries in various programming languages. This API abstracts away some of the low-level details of managing the WebSocket connection.

So while WebSockets and regular sockets both use TCP connections underneath, WebSockets provide a higher-level abstraction that is well-suited for real-time, interactive web applications. They offer features like low latency, efficient message transmission, and compatibility with web browsers and servers.


In this example, the client connects to the server via WebSocket, and when the WebSocket connection is established, it starts receiving messages from the server. The server sends each line with a 1-second pause between them. The client displays each received line in the console using `console.log()`.

If each client needs to receive different content and therefore requires its own URL, you have a few options for ensuring that each client connects to the correct URL:

1. **Dynamic URL Generation**: You can dynamically generate unique URLs for each client on the server-side and then provide these URLs to the corresponding clients. This could involve assigning unique identifiers to clients and using these identifiers to generate personalized URLs. Clients then use these URLs to establish WebSocket connections.

2. **Authentication and Authorization**: Authenticate clients when they connect to the server and then provide them with WebSocket URLs based on their authentication credentials. This ensures that each client only connects to URLs that correspond to the content they are authorized to access.

3. **Session Management**: Maintain session state on the server-side and associate each client session with specific content. When clients connect to the server, the server identifies the client's session and provides the appropriate WebSocket URL for the content associated with that session.

4. **URL Parameters**: Include parameters in the WebSocket URL that specify the content to be delivered to the client. Clients can then connect to URLs with the relevant parameters to receive the desired content.

5. **API Endpoint**: Provide an API endpoint that clients can use to request WebSocket URLs for specific content. Clients send requests to this endpoint with the necessary information (e.g., client ID, content type), and the server responds with the corresponding WebSocket URL.

The approach you choose depends on factors such as the complexity of your application, the scalability requirements, and the level of customization needed for each client's content.