import json
import logging

from logging_config import setup_logging

setup_logging()

from graph import graph

logger = logging.getLogger(__name__)


def main():
    logger.info("========== LOCAL TEST STARTED ==========")
    with open("input.json", "r", encoding="utf-8") as file:
        input_data = json.load(file)

    if not isinstance(input_data, dict):
        raise ValueError("input.json must contain a JSON object")

    chatqna = input_data.get("Chatqna")
    if chatqna is None:
        chatqna = input_data.get("chatqna", "")
    notes = input_data.get("Notes", "")
    logger.info(
        "Input loaded. MasterCaseId=%s, AutomationReportId=%s, Chatqna length=%d, Notes length=%d",
        input_data.get("MasterCaseId", ""),
        input_data.get("AutomationReportId", ""),
        len(str(chatqna or "")),
        len(str(notes or "")),
    )

    result = graph.invoke({"input_data": input_data})
    output = result.get("final_result", {})
    print("\n========================== FINAL OUTPUT ==========================\n")
    print(json.dumps(output, indent=4, ensure_ascii=False))
    with open("output.json", "w", encoding="utf-8") as file:
        json.dump(output, file, indent=4, ensure_ascii=False)
    logger.info("output.json saved successfully")
    logger.info("========== LOCAL TEST COMPLETED ==========")
    print("\nResult saved to output.json")
    print("Log saved to logs/contact_consent.log")


if __name__ == "__main__":
    main()
