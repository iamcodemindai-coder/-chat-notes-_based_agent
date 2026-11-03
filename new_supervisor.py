import logging

logger = logging.getLogger(__name__)

# Change only this value if the API field name changes later.
CHAT_FIELD = "Chatqna"
UNKNOWN_VALUES = {"", "unknown", "none", "null"}


def unknown(value):
    if value is None:
        return "Unknown"
    if isinstance(value, str) and value.strip().lower() in UNKNOWN_VALUES:
        return "Unknown"
    return value


def get_chatqna(input_data):
    """Read Chatqna. Lowercase chatqna is also supported."""
    if not isinstance(input_data, dict):
        return ""
    value = input_data.get(CHAT_FIELD)
    if value is None:
        value = input_data.get(CHAT_FIELD.lower(), "")
    return "" if value is None else str(value)


def get_notes(input_data):
    """Read Notes without modifying the original input value."""
    if not isinstance(input_data, dict):
        return ""
    value = input_data.get("Notes", "")
    return "" if value is None else str(value)


def create_chat_response(contact_result):
    """Preserve the new field-level candidates/status structure without flattening it."""
    contacts = contact_result.get("chat_response", [])
    if not isinstance(contacts, list):
        return []

    final_contacts = []
    for contact in contacts:
        if not isinstance(contact, dict):
            continue
        # Keep every contact field and nested candidate exactly as Contact Agent returned it.
        final_contacts.append({key: value for key, value in contact.items()})
    return final_contacts


def normalize_consent_value(value):
    if value is None:
        return "Unknown"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    value = str(value).strip().upper()
    if value == "YES":
        return "Yes"
    if value == "NO":
        return "No"
    if value in {"", "UNKNOWN", "NONE", "NULL"}:
        return "Unknown"
    return "Unknown"

#--------------------------------------------------------------------------------------------------------------------
#-----------------------THIS BELOW CODE IS CHANGED BY ME (3-NOV-2026)------------------------------------------------
#--------------------------------------------------------------------------------------------------------------------
def create_additional_fields(consent_result):
    """Preserve consent status, candidates, values, and evidence."""

    fields = consent_result.get("Additional Fields", [])
    values = {}

    # Read Consent Agent output without flattening nested fields.
    if isinstance(fields, list):
        for item in fields:
            if not isinstance(item, dict):
                continue

            for key, value in item.items():
                values[key.strip().lower()] = value

    field_mapping = {
        "permission_to_contact_complaint": "permission to contact complaint",
        "permission_to_contact_hcp": "permission to contact hcp",
        "permission_to_contact_patient": "permission to contact patient",
        "permission_to_contact_reporter": "permission to contact reporter",
        "permission_to_contact_reporter_via_text": "permission to contact via text",
    }

    def normalize_value(value):
        if value is None:
            return "Unknown"

        value = str(value).strip().upper()

        if value == "YES":
            return "Yes"
        if value == "NO":
            return "No"

        return "Unknown"

    def normalize_candidate(candidate):
        if not isinstance(candidate, dict):
            return{
                "value": "Unknown",
                "source": "",
                "evidence": [],
            }

        return {
            **candidate,
            "value": normalize_value(candidate.get("value")),
        }

    final_fields = {}

    for output_key, agent_key in field_mapping.items():
        field_data = values.get(agent_key)

        # New Consent Agent format: preserve status and candidates.
        if isinstance(field_data, dict) and isinstance(
            field_data.get("candidates"), list
        ):
            candidates = [
                normalize_candidate(candidate)
                for candidate in field_data["candidates"]
            ]

            status = str(field_data.get("status", "confirm")).strip().lower()
            if status not in {"confirm", "conflict"}:
                status = "confirm"

            # Recalculate conflict from the two source values.
            source_values = {
                candidate["value"].lower()
                for candidate in candidates
                if candidate["value"].lower() in {"yes","no"}
            }

            if source_values == {"yes", "no"}:
                status = "conflict"
            else:
                status = "confirm"

            final_fields[output_key] = {
                "status": status,
                "candidates": candidates,
            }

        else:
            # Backward compatibility for the old Consent Agent format.
            final_fields[output_key] = normalize_value(field_data)

    return final_fields

#-------------------------------------------------------------------------------------------------------------------------
#------------------------CODES CHANGES END HERE---------------------------------------------------------------------------
#-------------------------------------------------------------------------------------------------------------------------

def format_verbatim(value):
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if not isinstance(item, dict):
            continue
        bot = item.get("bot", "")
        user = item.get("user", "")
        if bot or user:
            result.append({"bot": bot, "user": user})
    return result


def combine_verbatim(contact_result, consent_result):
    contact = format_verbatim(contact_result.get("reported_verbatim", []))
    consent = format_verbatim(consent_result.get("Reported Verbatim", []))
    return contact + consent


def to_number(value):
    try:
        return float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def calculate_confidence(contact_result, consent_result):
    scores = []
    contact_score = to_number(contact_result.get("contact_confidence_score"))
    consent_score = to_number(consent_result.get("Consent Confidence Score"))
    if contact_score is not None:
        scores.append(contact_score)
    if consent_score is not None:
        scores.append(consent_score)
    if not scores:
        return 0
    return round(sum(scores) / len(scores), 2)


def create_final_output(input_data, contact_result, consent_result):
    """Create the fixed API response. No LLM is used here."""
    input_data = input_data if isinstance(input_data, dict) else {}
    contact_result = contact_result if isinstance(contact_result, dict) else {}
    consent_result = consent_result if isinstance(consent_result, dict) else {}

    output = {
        # Pass these IDs through unchanged from the incoming MuleSoft JSON.
        "MasterCaseId": input_data.get("MasterCaseId", ""),
        "AutomationReportId": input_data.get("AutomationReportId", ""),
        "Confidence": calculate_confidence(contact_result, consent_result),
        "Reported Verbatim": combine_verbatim(contact_result, consent_result),
        "ChatResponse": create_chat_response(contact_result),
        "Additional Fields": create_additional_fields(consent_result),
    }
    logger.info(
        "Final output created: MasterCaseId=%s, AutomationReportId=%s",
        output["MasterCaseId"], output["AutomationReportId"],
    )
    return output
