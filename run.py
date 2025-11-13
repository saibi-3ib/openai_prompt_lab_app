import os
from app import create_app

config_name = os.environ.get("FLASK_ENV", "development")
app = create_app(config_name)

if __name__ == "__main__":
    # Development: optionally enable adhoc SSL
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=app.config.get("DEBUG", False))