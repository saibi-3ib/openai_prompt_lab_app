from flask import current_app, jsonify

from . import api_bp


@api_bp.route("/get-prompts", methods=["GET"])
def get_prompts():
    """
    Placeholder endpoint for /api/get-prompts.
    Replace body with your real implementation (DB query / serialization).
    """
    current_app.logger.debug("api.get_prompts: returning placeholder empty list")
    return jsonify([]), 200
