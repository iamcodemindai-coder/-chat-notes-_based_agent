
import os
import json
import logging
import requests

from dotenv import load_dotenv
from urllib.parse import urlparse

from oauth_token_manager_2 import DatabricksTokenManager


logger = logging.getLogger(__name__)
load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_MODEL = os.getenv("OPENAI_MODEL")

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")


# ============================================================
# CONSENT FIELDS
# ============================================================

CONSENT_FIELDS = [
    "Permission To Contact HCP",
    "Permission To Contact Reporter",
    "Permission To Contact Patient",
    "Permission To Contact Complaint",
    "Permission To Contact Via Text",
]


# ============================================================
# CREATE TOKEN MANAGER
# ============================================================

def create_token_manager():

    if not OPENAI_BASE_URL:
        raise RuntimeError("OPENAI_BASE_URL is missing in .env")

    if not CLIENT_ID:
        raise RuntimeError("CLIENT_ID is missing in .env")

    if not CLIENT_SECRET:
        raise RuntimeError("CLIENT_SECRET is missing in .env")

    parsed_url = urlparse(OPENAI_BASE_URL)
    host = f"{parsed_url.scheme}://{parsed_url.netloc}"

    return DatabricksTokenManager(
        host=host,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        model_name=OPENAI_MODEL or "UNKNOWN"
    )


token_manager = create_token_manager()


# ============================================================
# CONSENT PROMPT
# ============================================================

CONSENT_PROMPT = """
You are a Consent Extraction Agent.

Your task is to extract the five consent permissions from the
supplied source text only.

Required permissions:

1. Permission To Contact HCP
2. Permission To Contact Reporter
3. Permission To Contact Patient
4. Permission To Contact Complaint
5. Permission To Contact Via Text

CONSENT VALUE RULES:

1. Each permission must have exactly one value:
   YES, NO, or UNKNOWN.

2. Never guess or invent consent.

3. Use the conversation meaning, including clear indirect answers,
   only when the meaning explicitly supports the consent decision.

4. A general statement or consent for one communication channel
   must not automatically establish consent for another channel.

5. Phone consent does not mean consent to contact via text.

6. If the caller is the Patient, Permission To Contact Patient
   is normally UNKNOWN unless another patient is explicitly
   discussed and the source supports a consent decision for that
   patient.

7. Do not assume consent merely because a person provided
   contact details or participated in the conversation.

8. Use the latest explicitly corrected consent value when
   the source contains a correction.

9. If the source does not provide sufficient evidence for a
   permission, return UNKNOWN with an empty evidence list.

10. Extract every permission independently. Do not copy a
    consent decision from one permission to another.

SOURCE RULES:

The input may be either a Chatqna conversation transcript
or free-text Notes.

For Chatqna:
- Extract only from the supplied bot/user conversation.
- Evidence must contain the exact bot and user text that
  supports the permission value.
- Preserve the original wording exactly.
- Include only directly relevant bot/user pairs.

For Notes:
- Extract only information explicitly stated in the notes.
- Evidence must contain exact note text, sentences, or
  substrings that directly support the permission value.
- Do not create or invent bot/user conversations.
- Do not use information from Chatqna or any other source.

EVIDENCE RULES:

1. Every permission must contain both "value" and "evidence".
2. Every YES or NO value must have directly supporting evidence.
3. If the value is UNKNOWN, evidence must be [].
4. Do not reuse unrelated evidence for a permission.
5. Do not include evidence that contradicts the selected value
   without resolving the contradiction from the supplied source.
6. If no reliable decision can be made, return UNKNOWN.

REPORTED VERBATIM RULES:

1. Preserve the existing Reported Verbatim functionality.
2. For Chatqna, include the exact bot/user conversation pairs
   used to determine or confirm consent.
3. Include all relevant qualifying confirmation conversations.
4. Each item must contain only "bot" and "user".
5. Do not invent confirmation conversations.
6. For Notes, Reported Verbatim must be [].
7. Field-level evidence and Reported Verbatim are separate.
8. Do not replace Reported Verbatim with field-level evidence.

CONFIDENCE RULES:

1. Return Consent Confidence Score in every response.
2. Use a numeric percentage score from 0 to 100.
3. Higher confidence means consent decisions are explicit and
   directly supported by the source.
4. Lower confidence means consent is ambiguous, incomplete,
   or mostly UNKNOWN.
5. Do not explain the score.

OUTPUT RULES:

Return valid JSON only, with exactly these top-level keys:
- Additional Fields
- Reported Verbatim
- Consent Confidence Score

Additional Fields must be a list containing exactly five objects,
one for each required permission, in the specified order.

Each permission object must have this structure:

{
  "Permission To Contact HCP": {
    "value": "YES",
    "evidence": [
      {
        "bot": "Exact bot question",
        "user": "Exact user response"
      }
    ]
  }
}

For Notes, the evidence list must contain exact strings instead:

{
  "Permission To Contact HCP": {
    "value": "YES",
    "evidence": [
      "Exact supporting note text."
    ]
  }
}

The example value YES is illustrative only. Select YES, NO,
or UNKNOWN according to the actual source.

Always include all five permissions.
Never omit a permission.
Never add extra permission fields.
Return JSON only without markdown or explanations.
"""


# ============================================================
# EMPTY SOURCE RESULT
# ============================================================

def empty_source_result():

    return {
        "Additional Fields": [
            {
                field: {
                    "value": "UNKNOWN",
                    "evidence": []
                }
            }
            for field in CONSENT_FIELDS
        ],
        "Reported Verbatim": [],
        "Consent Confidence Score": 0
    }


# ============================================================
# PARSE JSON RESPONSE
# ============================================================

def parse_json_response(content):

    if not content:
        raise ValueError("Model returned empty response")

    content = content.strip()

    if content.startswith("```"):
        lines = content.splitlines()
        content = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        ).strip()

    try:
        result = json.loads(content)

    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")

        if start < 0 or end <= start:
            raise ValueError(
                "No JSON object found in model response"
            )

        result = json.loads(content[start:end + 1])

    if not isinstance(result, dict):
        raise ValueError(
            "Model response is not a JSON object"
        )

    result.setdefault(
        "Additional Fields",
        empty_source_result()["Additional Fields"]
    )
    result.setdefault("Reported Verbatim", [])
    result.setdefault("Consent Confidence Score", 0)

    if not isinstance(result["Additional Fields"], list):
        result["Additional Fields"] = []

    if not isinstance(result["Reported Verbatim"], list):
        result["Reported Verbatim"] = []

    return result


# ============================================================
# CLEAN CONSENT VALUE
# ============================================================

def _clean_consent_value(value):

    if value is None:
        return "UNKNOWN"

    normalized = str(value).strip().upper()

    if normalized in {"YES", "NO"}:
        return normalized

    # Preserve the three-value consent contract.
    return "UNKNOWN"


# ============================================================
# NORMALIZE SOURCE CONSENT RESULT
# ============================================================

def _get_source_fields(result):

    """
    Convert the source-level Additional Fields list into a
    predictable field mapping.

    Supports both:
        {"Permission To Contact HCP": "YES"}

    and:
        {"Permission To Contact HCP": {
            "value": "YES",
            "evidence": [...]
        }}
    """

    fields = {}

    additional_fields = result.get("Additional Fields", [])

    if not isinstance(additional_fields, list):
        additional_fields = []

    for item in additional_fields:

        if not isinstance(item, dict):
            continue

        for field in CONSENT_FIELDS:

            if field not in item:
                continue

            raw_field = item[field]

            if isinstance(raw_field, dict):

                value = _clean_consent_value(
                    raw_field.get("value")
                )

                evidence = raw_field.get("evidence", [])

            else:
                # Backward compatibility with the old prompt.
                value = _clean_consent_value(raw_field)
                evidence = []

            if not isinstance(evidence, list):
                evidence = []

            fields[field] = {
                "value": value,
                "evidence": evidence
            }

    # Missing permissions must never be silently treated as YES/NO.
    for field in CONSENT_FIELDS:
        fields.setdefault(
            field,
            {
                "value": "UNKNOWN",
                "evidence": []
            }
        )

    return fields


# ============================================================
# CLEAN SOURCE-SPECIFIC EVIDENCE
# ============================================================

def _clean_evidence(evidence, source_name, value):

    if value == "UNKNOWN":
        return []

    if not isinstance(evidence, list):
        return []

    cleaned = []

    for item in evidence:

        if source_name == "chatqna":

            if isinstance(item, dict):

                bot = item.get("bot", "")
                user = item.get("user", "")

                if isinstance(bot, str) and isinstance(user, str):
                    if bot.strip() or user.strip():
                        cleaned.append({
                            "bot": bot,
                            "user": user
                        })

        else:

            if isinstance(item, str) and item.strip():
                cleaned.append(item)

    return cleaned


# ============================================================
# EXTRACT CONSENT FROM ONE SOURCE
# ============================================================

def _extract_one_source(source_text, source_name):

    if source_text is None:
        source_text = ""

    if not isinstance(source_text, str):
        source_text = str(source_text)

    if not source_text.strip():
        logger.info(
            "Consent Agent received empty %s source",
            source_name
        )
        return empty_source_result()

    access_token = token_manager.get_token()

    url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": CONSENT_PROMPT
            },
            {
                "role": "user",
                "content": (
                    f"SOURCE NAME: {source_name}\n"
                    "Extract all five consent permissions using "
                    "only the source text below.\n"
                    "Do not use information from another source.\n"
                    "If SOURCE NAME is notes, Reported Verbatim "
                    "must be an empty array. Use exact note text "
                    "for evidence, not invented bot/user pairs.\n\n"
                    "SOURCE TEXT START\n"
                    f"{source_text}\n"
                    "SOURCE TEXT END"
                )
            }
        ]
    }

    logger.info(
        "Calling Databricks Chat Completions API for %s",
        source_name
    )

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=120
    )

    logger.info(
        "Consent Agent %s API status=%s",
        source_name,
        response.status_code
    )

    response.raise_for_status()

    response_data = response.json()
    choices = response_data.get("choices", [])

    if not choices:
        logger.error(
            "Consent Agent %s response contains no choices",
            source_name
        )
        return empty_source_result()

    message = choices[0].get("message", {})
    content = message.get("content", "") or ""

    result = parse_json_response(content)

    # Normalize all five permissions and source-specific evidence.
    source_fields = _get_source_fields(result)

    normalized_fields = []

    for field in CONSENT_FIELDS:

        field_data = source_fields[field]
        value = field_data["value"]

        evidence = _clean_evidence(
            field_data["evidence"],
            source_name,
            value
        )

        normalized_fields.append({
            field: {
                "value": value,
                "evidence": evidence
            }
        })

    result["Additional Fields"] = normalized_fields

    # Notes must never contribute Chatqna reported verbatim.
    if source_name.casefold() == "notes":
        result["Reported Verbatim"] = []

    logger.info(
        "Consent Agent extraction completed for %s",
        source_name
    )

    return result


# ============================================================
# COMPARE CHATQNA AND NOTES
# ============================================================

def _build_compared_consents(chatqna_result, notes_result):

    chat_fields = _get_source_fields(chatqna_result)
    notes_fields = _get_source_fields(notes_result)

    compared = []

    for field in CONSENT_FIELDS:

        chat_data = chat_fields[field]
        notes_data = notes_fields[field]

        chat_value = chat_data["value"]
        notes_value = notes_data["value"]

        # Conflict ONLY when one source says YES and the other NO.
        if {chat_value, notes_value} == {"YES", "NO"}:
            status = "conflict"
        else:
            status = "confirm"

        chat_evidence = _clean_evidence(
            chat_data["evidence"],
            "chatqna",
            chat_value
        )

        notes_evidence = _clean_evidence(
            notes_data["evidence"],
            "notes",
            notes_value
        )

        compared.append({
            field: {
                "status": status,
                "candidates": [
                    {
                        "value": chat_value,
                        "source": "chatqna",
                        "evidence": chat_evidence
                    },
                    {
                        "value": notes_value,
                        "source": "notes",
                        "evidence": notes_evidence
                    }
                ]
            }
        })

    return compared


# ============================================================
# MAIN CONSENT AGENT
# ============================================================

def extract_consent(chatqna, notes=""):

    """
    Extract consent independently from Chatqna and Notes,
    then compare all five permissions.

    Keeps the existing function name and first argument
    compatible with the previous caller.
    """

    logger.info(
        "CONSENT AGENT STARTED: independent Chatqna and Notes extraction"
    )

    try:
        chatqna_result = _extract_one_source(
            chatqna,
            "chatqna"
        )

    except Exception:
        logger.exception(
            "Consent extraction failed for Chatqna"
        )
        chatqna_result = empty_source_result()

    try:
        notes_result = _extract_one_source(
            notes,
            "notes"
        )

    except Exception:
        logger.exception(
            "Consent extraction failed for Notes"
        )
        notes_result = empty_source_result()

    compared_consents = _build_compared_consents(
        chatqna_result,
        notes_result
    )

    # Preserve Chatqna's existing confidence and reported verbatim.
    result = {
        "Additional Fields": compared_consents,
        "Reported Verbatim": chatqna_result.get(
            "Reported Verbatim",
            []
        ),
        "Consent Confidence Score": chatqna_result.get(
            "Consent Confidence Score",
            0
        )
    }

    logger.info(
        "CONSENT AGENT COMPLETED: compared %d permissions",
        len(compared_consents)
    )

    return result
