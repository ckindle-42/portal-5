import logging
import uvicorn
from portal_pipeline.router_pipe import app

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9099)

def main():
    uvicorn.run(app, host="0.0.0.0", port=9099)
