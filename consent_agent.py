
import os
import json
import logging
import requests
import time

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
# CONSENT FIELDS
# ============================================================

CONSENT_FIELDS = [
    "permission_to_contact_hcp",
    "permission_to_contact_reporter",
    "permission_to_contact_patient",
    "permission_to_contact_complaint",
    "permission_to_contact_reporter_via_text",
]


# ============================================================
# CONSENT PROMPT
# ============================================================

CONSENT_PROMPT = """
You are a Consent Extraction Agent.

Your task is to accurately extract consent-related information from a conversation transcript between a bot and a user.

=======================================================================================================================================
CONVERSATION RULES
=======================================================================================================================================

Participants:
- bot
- user

The bot asks questions and the user responds.

User responses may be:
- Direct
- Indirect
- Conversational
- Incomplete
- Corrective
- Confirmatory
- Affected by speech-to-text errors

Determine the user's true intent using conversation context.

Always prioritize conversational meaning over exact wording.

==========================================================================================================================================
TRANSCRIPT CHARACTERISTICS
==========================================================================================================================================

The transcripts is generated from a speech-to-text system and may contain:
- Recognition errors
- Spelling mistakes
- Grammar mistakes
- Incorrect punctuation
- Repeated text
- Interruptions
- Mixed languages
- Foreign words
- Background noise
- Incomplete sentences

Examples:

"God did not extend it"
may actually mean:
"Guard did not extend it"

Focus on meaning and intent rather than literal wording.

===========================================================================================================================================
CALLER IDENTIFICATION
===========================================================================================================================================

The user will always be one of:

1. Patient
2. Healthcare Provider (HCP)

Determine caller type before extracting any consent fields.

PATIENT CALLER

- Patient is typically the Reporter.
- Permission To Contact Reporter refers to permission to permission to contact the Patient.
- Permission To Contact HCP refers to permission to contact the Patient's Healthcare Provider.

HCP CALLER

- HCP is typically the Reporter.
- Permission To Contact Reporter refers to permission to contact the HCP.
- Permission To Contact Patient refers to permission to contact the Patient.

=============================================================================================================================================
FIELDS TO EXTRACT
=============================================================================================================================================

1. Permission To Contact HCP
2. Permission To Contact Reporter
3. Permission To Contact Patient
4. Permission To Contact Complaint
5. Permission To Contact Via Text
6. Reported Verbatim
7. Consent Confidence Score

UNKNOWN = insufficient reliable evidence to determine YES or NO.

===============================================================================================================================================
FIELD DEFINITIONS
===============================================================================================================================================

Permission To Contact HCP

YES:
User allows Amgen, Safety Team, Quality Team, Pharmacy, Follow-up Team, or equivalent parties to contact the Healthcare Provider.

NO:
User explicitly refuses such contact.

UNKNOWN:
Insufficient reliable evidence.

------------------------------------------------------------------------------------------------------------------------------------------------
Permission To Contact Reporter

YES:
User agrees to follow-up, future contact, additional questions, future communication, Safety Team contact, Quality Team contact, or equivalent case-related contact.

NO:
User refuses future contact.

UNKNOWN:
Insufficient reliable evidence.

-------------------------------------------------------------------------------------------------------------------------------------------------

Permission To Contact Patient

IMPORTANT:

This field is generally applicable only when the caller is an HCP. 

If Caller Type = Patient:

Permission To Contact Patient should normally be UNKNOWN unless another patient is explicitly discussed and permission is clearly granted or denied.

YES:
HCP allows contact with the patient.

NO:
HCP refuses patient contact.

UNKNOWN:
Insufficient reliable evidence.

----------------------------------------------------------------------------------------------------------------------------------------------------

Permission To Contact Complaint

YES:
User allows future contact regarding:
- Complaint
- Product Issue
- Device Issue
- Quality Issue
- Adverse Event
- Safety Report
- Investigation
- Replacement Request
- Case Follow-Up

NO:
User refuses complaint-related follow-up.

UNKNOWN:
Insufficient reliable evidence.

------------------------------------------------------------------------------------------------------------------------------

Permission To Contact Via Text

YES:
User agrees to receive:
- Text messages
- SMS messages
- Survey links
- Reference numbers by text
- Updates by text

NO:
User refuses text communication.

UNKNOWN:
Text communication is not clearly discussed.

=================================================================================================================================
PHONE CONSENT VS TEXT CONSENT
=================================================================================================================================

Phone consent and text consent are separate permissions.

Example:

bot:
May we contact you by phone?

user:
Yes

Permission To Contact Via Text - UNKNOWN

----------------------------------------------------------------------------------------------------------------------------------

bot:
If you consent to texting, you may receive a text message today. Is that okay?

user:
Yes

Permission To Contact Via Text = YES

Never infer texting consent from phone consent.

=======================================================================================================================================
CONSENT INTERPRETATION
========================================================================================================================================

Do not require the exact phrase:

"I consent"

Treat clear affirmations as YES when they answer a consent-related question.

Examples include:

- Yeah
- Yup
- Sure
- Correct
- Right
- Absolutely
- Fine
- That's fine
- That is fine
- Sounds good
- Of course
- Go ahead
- Please do
- You can
- They can
- I agree
- That works
- Okay sure
- Yes sir
- Yes ma'am
- Yes buddy
- Yes boss
- Ja
- Ja, schön

Treat clear refusals as NO when they answer a consent-related question.

Examples include:

- No
- Nope
- No thank you
- Not really
- I do not want that
- Do not contact me
- Not interested
- I refuse
- I'd rather not

Use intent and context.

Never guess.

If evidence is unclear, return UNKNOWN.

============================================================================================================================================================
LANGUAGE RULE
=============================================================================================================================================================


If the primary evidence for a consent decision is derived from:

- Non-English text
- Foreign-language phrases
- Mixed-language responses

return UNKNOWN unless the consent meaning is clearly and reliably expressed. 

UNKNOWN is preferred over guessing.

=================================================================================================================================================================
REPORTED VERBATIM
==================================================================================================================================================================

Reported Verbatim must only contain evidence used to determine:

- Permission To Contact HCP
- Permission To Contact Reporter
- Permission To Contact Patient
- Permission To Contact Complaint
- Permission To Contact Via Text

Each entry must contain BOTH:

1. The bot's consent-related question
2. The user's response

Capture exchanges involving:

- HCP contact permission
- Reporter contact permission
- Patient contact permission
- Safety Team follow-up
- Quality Team follow-up
- Complaint follow-up
- Additional information requests
- Future communication
- Investigation follow-up
- Text messages
- SMS messages
- Survey texts
- Reference number texts

Examples:

bot:
Do you consent to Amgen contacting your healthcare provider?

user:
Yes they can.

CAPTURE

-------------------------------------------------------------------------------------------------------------------------------------------------------------------

bot:
May our safety team contact you if additional information is needed?

user:
Yeah sure.

CAPTURE

---------------------------------------------------------------------------------------------------------------------------------------------------------------------

bot:
May Amgen contact you again regarding this report?

user:
That is fine.

CAPTURE

-----------------------------------------------------------------------------------------------------------------------------------------------------------------------

bot:
If you consent to texting, you may receive a text message today. Is that okay?

user:
Yes.

CAPTURE

-----------------------------------------------------------------------------------------------------------------------------------------------------------------------

DO NOT CAPTURE:

- Name confirmations
- Address confirmations
- DOB confirmations
- Email confirmations
- Phone number confirmations
- Shipping confirmations
- Spelling confirmations
- Product information confirmations
- Complaint descriptions
- Medical history
- Device descriptions
- Lot numbers
- Expiration dates

Examples:

bot:
Did I spell your name correctly?

user:
Correct.

DO NOT CAPTURE

----------------------------------------------------------------------------------------------------------------------------------------------------------------------

bot:
Is your phone number correct?

user:
Yeah.

DO NOT CAPTURE


=====================================================================================================================================================================
REPORTED VERBATIM RULES
======================================================================================================================================================================

- Capture only consent-related evidence.
- Capture only exchanges used to determine consent fields.
- Include both bot and user text.
- Preserve original wording.
- Preserve chronological order.
- Do not rewrite.
- Do not summarize.
- Include direct and indirect responses.
- Include YES evidence.
- Include NO evidence.
- Include UNKNOWN evidence only when the response directly caused UNKNOWN.
- Exclude unrelated confirmations.
- Only capture exchanges where the user's consent-related response is clearly expressed in English.
- Do not capture entries where the user's response is primarily non-English, a foreign-language affirmation, or a foreign-language phrase.
- Minor English spelling mistakes, speech-to-text errors, and pronunciation-based English variations may still be captured.

If no consent-related evidence exists:

Return an empty array.

=====================================================================================================================================================================
FIELD LEVEL EVIDENCE RULES
=====================================================================================================================================================================

Each consent field must contain only the evidence used to determine that specific field.

Do not copy all evidence to all fields.

Permission To Contact HCP:
Include only evidence used to determine permission to contact the healthcare provider.

Permission To Contact Reporter:
Include only evidence used to determine permission for future follow-up with the reporter.

Permission To Contact Patient:
Include only evidence used to determine permission to contact the patient.

Permission To Contact Complaint:
Include only evidence involving complaint follow-up, safety follow-up, quality follow-up,
adverse event follow-up, replacement follow-up, or investigation follow-up.

Permission To Contact Via Text:
Include only evidence involving text messages, SMS messages, surveys by text, links by text, or reference numbers sent by text.

Evidence must contain the exact bot question and exact user response.
Example:

{
    "Permission To Contact Via Text": {
        "value": "YES",
        "evidence": [
            {
                "bot": "If you consent to texting, you may receive a text today. Is that okay?",
                "user": "Yes"
            }
        ]
    }
}

If no evidence exists for a field, return an empty evidence array.

Do not place unrelated evidence under a field.

================================================================================================================================================================
CONSENT CONFIDENCE SCORE
================================================================================================================================================================

Generate a numeric confidence score from 0-100.

The score represents confidence in the entire extraction output.

Consider:

- Caller identification confidence
- Evidence quality
- Explicit consent answers
- Explicit refusal answers
- Transcript quality
- Speech-to-text corruption
- Ambiguity
- Consistency
- Multiple supporting transcript segments

Guidelines:

95-100
- Clear caller type
- Clear evidence
- Explicit answers
- Consistent conversation

85-94
- Minor ambiguity
- Strong supporting evidence

70-84
- Moderate ambiguity
- Indirect answers
- Noticeable transcript issues

50-69
- Significant ambiguity
- Weak evidence

0-49
- Highly unreliable transcript
- Insufficient evidence

Return only an integer.

Do not inflate the score.

==================================================================================================================================================================
DECISION PROCESS
==================================================================================================================================================================

For every consent field:

1. Identify the relevant question.
2. Identify the user's response.
3. Interpret intent.
4. Assign YES, NO, or UNKNOWN.

Rules:

- Use full conversation context.
- Consider direct responses.
- Consider indirect responses.
- Consider corrections.
- Understand intent.
- Never guess.
- UNKNOWN is preferred over incorrect values.
- Do not infer one consent field from another.

=================================================================================================================================================================
FINAL VALIDATION
=================================================================================================================================================================

Before returning output:

1. Determine caller type.
2. Validate each consent field independently.
3. Ensure supporting evidence exists.
4. Remove assumptions.
5. Use UNKNOWN when evidence is weak.
6. Phone consent must not imply text consent.
7. Patient callers should normally have:

Permission To Contact Patient = UNKNOWN

unless explicit evidence exists.

===================================================================================================================================================================
OUTPUT RULES
====================================================================================================================================================================

Return ONLY valid JSON.

Do not return:
- Explanations
- Notes
- Reasoning
- Markdown
- Additional text

Return exactly:

{
    "Additional Fields": [
        {
            "Permission To Contact HCP": {
                "value":'
                "evidence": []
            }
        },
        {
            "Permission To Contact Reporter": {
                "value": ""
                "evidence": []
            }
        },
        {
            "Permission To Contact Patient": {
                "value": ""
                "evidence": []
            }
        },
        {
            "Permission To Contact Via Text": {
                "value": ""
                "evidence": []
            }
        },
    ],
    "Consent Confidence Score": 0
}
"""


# ============================================================
# EMPTY SOURCE RESULT
# ============================================================

def empty_source_result():

    return {
        "Additional Fields": [
            {
                "Permission To Contact HCP": {
                    "value": "UNKNOWN",
                    "evidence": []
                }
            },
            {
                "Permission To Contact Reporter": {
                    "value": "UNKNOWN",
                    "evidence": []
                }
            },
            {
                "Permission To Contact Patient": {
                    "value": "UNKNOWN",
                    "evidence": []
                }
            },
            {
                "Permission To Contact Complaint": {
                    "value": "UNKNOWN",
                    "evidence": []
                }
            },
            {
                "Permission To Contact Via Text": {
                    "value": "UNKNOWN",
                    "evidence": []
                }
            },
        ],
        "Consent Confidence Score": 0
    }

# ============================================================
# PARSE JSON RESPONSE
# ============================================================

def parse_json_response(text):

    if not text:
        raise ValueError(
            "Model returned empty response"
        )

    text = text.strip()

    if text.startswith("```"):

        lines = text.splitlines()

        lines = [
            line
            for line in lines
            if not line.strip().startswith("```")
        ]

        text = "\n".join(lines).strip()

    try:

        data = json.loads(text)

        if isinstance(data, dict):
            return data

    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
            
        raise ValueError(
                "No JSON object found in model response"
        )

    data = json.loads(text[start:end + 1])

    if not isinstance(data, dict):
        raise ValueError(
            "Model response is not a JSON object"
        )

    return data

# ============================================================
# HELPERS
# ============================================================

def _clean_value(value):

    if value is None:
        return "UNKNOWN"

    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.lower() in {
            "",
            "unknown",
            "none",
            "null",
            "n/a",
            "na"
        }:
            return "UNKNOWN"
        return cleaned
    return value


def _comparison_key(value):

    if isinstance(value,str):

        return " ".join(
            value.strip().casefold()split()
        )

    return value

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

    url = (
        f"{OPENAI_BASE_URL.rstrip('/')}"
        "/chat/completions"
    )

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
                    f"SOURCE NAME: {source_name}\n\n"
                    "SOURCE START\n"
                    f"{source_text}"
                    "\nSOURCE END"
                )
            }
        ]
    }

    logger.info(
        "Calling Databricks chat Completions API for %s",
        source_name
    )

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=120
    )

    response.raise_for_status()

    response_data = response.json()

    choices = response_data.get(
        "choices",
        []
    )

    if not choices:

        logger.error(
            "Consent Agent %s response contain no choices",
            source_name
        )

        return empty_source_result()

    message = choices[0].get(
        "message",
        {}
    )

    content = message.get(
        "content",
        ""
    ) or ""

    result = parse_json_response(content)

    result.setdefault(
        "Additional Fields"
        empty_source_result()["Additional Fields"]
    )

    result.setdefault(
        "Consent Confidence Score",
        0
    )

    return result

# ============================================================
# COMPARE CHATQNA AND NOTES
# ============================================================

def _build_compared_consents(chatqna_result, notes_result):

    chat_fields = chatqna_result.get(
        "Additional Fields",
        []
    )
    notes_fields = notes_result.get(
        "Additional Fields",
        []
    )

    field_mapping = {
        "permission_to_contact_hcp":"Permission To Contact HCP",
        "permission_to_contact_reporter":"Permission To Contact reporter",
        "permission_to_contact_patient":"Permission To Contact Patient",
        "permission_to_contact_complaint":"Permission To Contact Complaint",
        "permission_to_contact_via_text":"Permission To Contact Via Text"
    }

    compared_fields = {}

    for output_field, original_field in field_mapping.items():

        chat_value = "UNKNOWN"
        notes_value = "UNKNOWN"

        chat_evidence = []
        notes_evidence = []

        # ChatQna
        for item in chat_fields:
            if (
                isinstance(item, dict)
                and original_field in item
            ):

                field_data = item.get(
                    original_field
                )

                if isinstance(field_data, dict):

                    chat_value = _clean_value(
                        field_data.get("value")
                    )

                    chat_evidence = field_data.get(
                        "evidence",
                        []
                    )

                else:

                    chat_value = _clean_value(
                        field_data
                    )

                break

            # Notes
            for item in notes_fields:

                if (
                    isinstance(item,dict)
                    and original_field in item
                ):

                    field_data = item.get(
                        original_field
                    )

                    if isinstance(field_data,dict):

                        notes_value = _clean_value(
                            field_data.get("value")
                        )

                        notes_evidence = field_data.get(
                            "evidence",
                            []
                        )

                    else:

                        notes_value = _clean_value(
                            field_data
                        )

                    break

            if (
                chat_value != "UNKNOWN"
                and notes_value != "UNKNOWN"
                and _comparison_key(chat_value)
                != _comparison_key(notes_value)
            ):

                status = "conflict"

            else:

                status = "confirm"

            compared_fields[output_field] = {
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

        return compared_fields

# =========================================================================================================================================
# EXTRACT CONSENT
# =========================================================================================================================================

def extract_consent(chatqna, notes=""):
    start_time = time.time()

    logger.info(
        "CONSENT AGENT STARTED"
    )

    try:

        chatqna_result = _extract_one_source(
            chatqna,
            "chatqna"
        )

    except Exception:

        logger.exception(
            "Consent extraction failed for chatqna"
        )

        chatqna_result = empty_source_result()

    try:

        notes_result = _extract_one_source(
            notes,
            "notes"
        )

    except Exception:

        logger.exception(
            "Consent extraction failed for notes"
        )

        notes_result = empty_source_result()

    compared_fields = _build_compared_consents(
        chatqna_result,
        notes_result
    )

    result = {
        "Additional Fields": compared_fields,
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
        "CONSENT AGENT COMPLETED"
    )

    execution_time = round(
        time.time() - start_time,
        2
    )

    logger.info(
        "CONSENT AGENT EXECUTION TIME %.2f seconds",
        execution_time
    )

    return result
