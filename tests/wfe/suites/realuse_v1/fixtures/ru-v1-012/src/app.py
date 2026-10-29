from flask import Flask

app = Flask(__name__)


@app.get("/")
def home():
    return {"message": "service is running"}
