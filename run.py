# Thin startup wrapper delegating to app.factory.create_app
from app.factory import create_app

app = create_app()

if __name__ == "__main__":
    # local dev only
    app.run(host="127.0.0.1", port=5000, debug=True)
