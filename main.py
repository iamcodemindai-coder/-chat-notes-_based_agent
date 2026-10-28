import logging

from flask import Flask, request, jsonify

from logging_config import setup_logging

setup_logging()

from graph import graph

logger = logging.getLogger(__name__)
app = Flask(__name__)


@app.route("/", methods=["GET"])
def status():
    return "OK", 200


@app.route("/ccai", methods=["POST"])
def process_request():
    input_data = {}
    try:
        input_data = request.get_json(force=True)
        if not isinstance(input_data, dict):
            return jsonify({"error": "Request body must be a JSON object"}), 400

        chatqna = input_data.get("Chatqna")
        if chatqna is None:
            chatqna = input_data.get("chatqna", "")
        notes = input_data.get("Notes", "")

        logger.info(
            "Received /ccai request. MasterCaseId=%s, AutomationReportId=%s, Chatqna length=%d, Notes length=%d",
            input_data.get("MasterCaseId", ""),
            input_data.get("AutomationReportId", ""),
            len(str(chatqna or "")),
            len(str(notes or "")),
        )

        result = graph.invoke({"input_data": input_data})
        output = result.get("final_result", {})
        return jsonify(output), 200

    except Exception:
        logger.exception("Request processing failed")
        input_data = input_data if isinstance(input_data, dict) else {}
        return jsonify({
            "MasterCaseId": input_data.get("MasterCaseId", ""),
            "AutomationReportId": input_data.get("AutomationReportId", ""),
            "Confidence": 0,
            "Reported Verbatim": [],
            "ChatResponse": [],
            "Additional Fields": {
                "permission_to_contact_complaint": "Unknown",
                "permission_to_contact_hcp": "Unknown",
                "permission_to_contact_patient": "Unknown",
                "permission_to_contact_reporter": "Unknown",
                "permission_to_contact_reporter_via_text": "Unknown",
            },
        }), 500


if __name__ == "__main__":
    logger.info("Starting API on port 5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
