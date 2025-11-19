# wsgi.py
# Import the application object expected by gunicorn (wsgi:app)
# Adjust the import below to match how your app is created in this repo.

try:
    # If your app is created as a global `app` in run.py
    from run import app
except Exception:
    try:
        # If your app uses an application factory create_app()
        from run import create_app

        app = create_app()
    except Exception:
        # Fallback: attempt to import Flask app from other common modules
        try:
            from app import create_app as _create_app

            app = _create_app()
        except Exception:
            raise
