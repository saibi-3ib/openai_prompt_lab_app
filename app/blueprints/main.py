from flask import Blueprint, jsonify, render_template

main_bp = Blueprint("main", __name__, url_prefix="")


@main_bp.route("/")
def index():
    # If you have an index template, render it; otherwise return JSON for smoke test
    try:
        return render_template("index.html")
    except Exception:
        return jsonify({"status": "ok", "msg": "Hello from main blueprint"})
