import os

# FastAPI TestClient uses this synthetic hostname and never binds a socket.
os.environ["API_ALLOWED_HOSTS"] = "localhost,127.0.0.1,::1,testserver"
