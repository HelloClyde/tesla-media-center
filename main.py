from flask_app import app


if __name__ == '__main__':
    # Keep `python main.py` working, but route it to the only supported backend.
    app.run(host='0.0.0.0', threaded=True, port=8080)
