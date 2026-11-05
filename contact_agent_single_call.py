import json
import logging
import os
from urllib.parse import urlparse
import time

import requests
from dotenv import load_dotenv

from oauth_token_manager_2 import DatabricksTokenManager
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)
load_dotenv()

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_MODEL = os.getenv("OPENAI_MODEL")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

CONTACT_FIELDS = [
    "contact_type",
    "contact_role",
    "first_name",
    "last_name",
    "phone_number",
    "additional_phone_number",
    "email_address",
    "date_of_birth",
    "gender",
    "address",
    "street",
    "city",
    "zip_postal_code",
    "state_province",
    "country",
]

CONTACT_PROMPT = """You are a Contact Information Extraction Agent.

Your task is to identify and extract contact information from the transcript.

Determine the contact_type for each contact found.

Allowed contact_type values:

- Patient
- HCP
- Other HCP

HCP includes:

- Doctor
- Physician
- Nurse
- Healthcare Professional
- Healthcare Provider

Other HCP includes:

- Wife
- Husband
- Spouse
- Mother
- Father
- Brother
- Sister
- Son
- Daughter
- Friend
- Relative
- Family Member
- Caregiver
- Guardian
- Representative


Contact Identification Rules:

1. Create a contact record whenever a Patient, HCP or Other HCP is identified.

2. Even if no contact details are available, create the contact record and populate unavailable fields with "unknown".

3. Do not invent or infer contact details.

4. If the contact type cannot be determined, use "unknown".

5. Return separate contact records for each distinct Patient, HCP or Other HCP referenced in the transcript.

6. Preserve the order of appearance from the transcript.

7. Contacts must be returned in the same sequence in which they are first mentioned in the transcript.

8. Do not reorder contacts by contact_type or any other criteria.

9. The order of objects in chat_response must exactly match the order in which contacts are first identified in the transcript.

10. The patient being discussed and the person communicating may be different contacts and should be treated separately when both can be identified.

11. Only assign contact_type as "Patient" when the transcript explicitly indicates that the individual is the patient.

12. Only assign contact_type as "HCP" when the individual is explicitly identified as a healthcare professional.

13. Assign contact_type as "Other HCP" when the individual is communicating on behalf of a patient and is not explicitly identified as the patient or as an HCP.

14. Spouses, wives, husbands, mothers, fathers, brothers, sisters, sons, daughters, caregivers, guardians, friends, relatives, family members, and representatives communicating on behalf of a patient should be classified as "Other HCP" unless explicitly identified as the patient or as an HCP.

15. Do not automatically classify spouses, caregivers, relatives, representatives, or family members as Patients.


Email Resolution Rules:

1. When an email address contains a placeholder or reference to a previously provided name component, resolve the placeholder using the corresponding name already provided by the same contact.

2. Examples:

    - If first_name = John and last_name = Smith:
    - mylastname@gmail.com -> smith@gmail.com
    - myfirstname@gmail.com -> john@gmail.com
    - myfullname@gmail.com -> johnsmith@gmail.com

3. Apply the same logic to similar references that clearly refer to previously provided name information.

4. Apply this only when the placeholder clearly refers to information explicitly provided earlier in the transcript.

5. Do not guess missing values.

6. If the email address is explicitly provided as a complete literal email address, use the value exactly as provided.



Extract the following fields:

for every field return:

- value
- evidence

Evidence must contain only the source text that directly supports the extracted value.

Required fields:

- contact_type
- contact_role
- first_name
- last_name
- phone_number
- additional_phone_number
- email_address
- date_of_birth
- gender
- address
- street
- city
- zip_postal_code
- state_province
- country


Contact Role Rules:

1. Determine the contact_role for each contact based on the contact_type and the information explicitly stated in the transcript.

2. Do NOT use "Requestor" as a contact_role.

3. Do NOT use "Other" as a contact_role.

4. If contact_type is "HCP", the only allowed professional contact_role values are:

    - Pharmacist
    - Prescriber
    - Physician
    - Reporter

5. If contact_type is "Patient", the only allowed contact_role values are:

    - Patient
    - Complainant
    - Reporter

5a. If contact_type is "Other HCP", the only allowed contact_role value is:

    - Reporter

6. If the contact is an HCP and is explicitly identified as a pharmacist, use "Pharmacist".

7. If the contact is an HCP and is explicitly identified as a prescriber or as the person who prescribed the medication or treatment, use "Prescriber".

8. If the contact is an HCP and is explicitly identified as a physician, doctor, or physician, use "Physician".

9. "Pharmacist", "Prescriber", and "Physician" are mutually exclusive professional HCP roles. Do not assign one of these roles to an HCP unless the transcript explicitly supports that specific role.

10. A Pharmacist must NOT be assigned "Physician" or "Prescriber" unless the transcript explicitly identifies that same person as a Physician or Prescriber. Do not infer one professional role from another.

11. A Physician must NOT be assigned "Pharmacist" or "Prescriber" unless the transcript explicitly identifies that same person as a Pharmacist or Prescriber.

12. A Prescriber must NOT be assigned "Pharmacist" or "Physician" unless the transcript explicitly identifies that same person as a Pharmacist or Physician.

13. If an HCP is the person who makes the call or reports the case, add "Reporter" to the contact_role.

14. If a Patient is the person who makes the call or reports the case, add "Reporter" to the contact_role.

15. If the contact is the Patient, always include "Patient" in the contact_role.

16. If the Patient is also the person making or submitting the complaint, include "Complainant" in the contact_role.

17. If the Patient is the caller/reporter and is also making a complaint, the contact_role must contain all applicable roles in one string:
    "Patient, Complainant, Reporter"

18. If the Patient is the caller but is not making a complaint, the contact_role must be:
    "Patient, Reporter"

19. If an HCP is the caller/reporter and is a Pharmacist, the contact_role must be:
    "Pharmacist, Reporter"

20. If an HCP is the caller/reporter and is a Prescriber, the contact_role must be:
    "Prescriber, Reporter"

21. If an HCP is the caller/reporter and is a Physician, the contact_role must be:
    "Physician, Reporter"

22. Reporter should only be added when the transcript supports that the specific contact is the person who called, reported the event, or provided the case information.

23. Complainant should only be added when the transcript supports that the specific contact made or submitted the complaint.

24. Do not assign "Complainant" simply because the contact is a Patient.

25. Do not assign "Reporter" simply because the contact is a Patient or HCP. The transcript must indicate that the person is the caller/reporter.

25a. If contact_type is "Other HCP" and the individual is the caller, reporter, or source of the information, assign "Reporter".

25b. Do not assign the following roles to an Other HCP contact:

    - Patient
    - Complainant
    - Physician
    - Prescriber
    - Pharmacist

26. Multiple applicable roles must be returned together as a single string in the "contact_role" field.

27. Keep the roles specific to the same contact. Do not combine roles belonging to different people.

28. Do not assign roles based on assumptions, common practice, or job knowledge.

29. Use only the role information explicitly supported by the transcript.

30. Do not use any contact_role value outside the allowed values defined above.

30a. Valid Other HCP examples:

    - Reporter

31. If contact_type is "HCP" and no specific professional role is explicitly identified, use "Reporter" only if the HCP is explicitly the caller/reporter. Otherwise return "unknown".

32. If contact_type is "Patient" and the patient is explicitly identified as the patient but no caller/complainant information is available, return "Patient".

32a. If contact_type is "Other HCP" and the individual is explicitly identified as the caller, reporter, or souce of the information, return "Reporter".

32b. If contact_type is "Other HCP" and no role can be explicitly determind, return "Unknown"

33. The final contact_role must be a single string. If multiple roles apply, separate them using a comma and a space.

34. Never return contact_role as an array.

35. Never return "Requestor".

36. Never return "Other".


Name Rules:

1. Split names into first_name and last_name.

2. Do not return a full_name field.


Address Rules:

1. address = complete address.

2. street = street portion only.

3. city = city only.

4. zip_postal_code = postal code or ZIP code only.

5. state_province = state or province only.

6. country = country only.


Date of Birth Rules:

1. Date of birth must always be returned in MM/DD/YY format.

2. Convert any identified date of birth into MM/DD/YY format.

3. Examples:

- September 5, 1990 -> 09/05/90
- Sep 5, 1990 -> 09/05/90
- 1990-09-05 -> 09/05/90
- 5 September 1990 -> 09/05/90

4. If the complete date of birth is not available, return "unknown".

5. Do not guess missing day, month, or year values.


Confidence Score Rules:

1. Provide an overall contact_confidence_score for the entire extraction.

2. contact_confidence_score must be returned as a percentage between 0% and 100%.

3. The score should reflect confidence in the overall accuracy of the identified contacts and extracted contact details.

4. Higher confidence:
    - Contact type is explicitly identified.
    - Contact information is clearly stated.
    - Multiple contact attributes are available.

5. Lower confidence:
    - Contact type is ambiguous.
    - Contact details are incomplete or unclear.
    - Information is indirect or uncertain.

6. Examples:
    - 98%
    - 75%
    - 20%

7. Return the percentage symbol (%) with the score.

8. contact_confidence_score must always be returned.

9. Return only the percentage value without any explanation.


General Rules:

1. Ignore agent information.

2. Ignore filler words such as:
    - umm
    - ahh
    - hmm
    - let me think

3. Use the latest corrected value if information is updated.

4. Use "unknown" for missing information.

5. Do not guess values.

6. Return valid JSON only.

7. Return all contacts found in the transcript.

8. Return only the JSON objects. Do not include explanations, comments, markdown, or additional text.

9. Ensure all output field names exactly match the specified output schema.

10. Include contact_confidence_score in every response, even when confidence is low.

11. contact_confidence_score must be returned as a percentage string including the % symbol.

12. If a field value is unavailable, return the exact string "unknown".


Reported Verbatim Rules:

1. Create a reported_verbatim section.

2. For every extracted contact field whose final value is not "unknown", include the corresponding bot and user conversation pair that led to the value being confirmed, accepted, or validated.

3. Include all qualifying confirmation conversations, not just a subset.

4. User confiramtion may be direct or indirect.

5. Examples of confiramtion include:
    - Yes
    - Yeah
    - Yep
    - Correct
    - Right
    - Agreed
    - Absolutely
    - Exactly
    - Ja
    - That's correct
    - Yes, correct
    - Yes, sir
    - That's fine
    - Looks good

6. Do not include records where the final extracted value is "unknown".

7. Every extracted field whose final value is not "unknown" must be traceable to a confiramtion conversation in reported_verbatim whenever such a confirmation exists in the transcript.

8. If multiple confiramtions contribute to a final extracted value, include all relevant confirmation conversations.

9. Capture only:
    - bot
    - user

10. Preserve the original wording exactly as it appears in the transcript.

11. The number of reported_verbatim records should correspond to all confirmed contact information that resulted in a non-"unknown" extracted value.

12. Do not omit confirmed contact information simply because multiple fields belong to the same contact.

FIELD-LEVEL EVIDENCE RULES:

Every extracted field must contain:

- value
- evidence

Structure:

{
    "field_name": {
        "value": "<extracted value>",
        "evidence": [...]
    }
}

CHATQNA EVIDENCE

For Chatqna extraction:

Use the exact bot/user conversation that supports the field.

Example:

{
    "first_name": {
        "value": "Mary",
        "evidence":[
            {
                "bot": "Can you please confirm your first name?",
                "user": "Mary"
            }
        ]
    }
}

NOTES EVIDENCE

For Notes extraction:

Use the exact notes text that supports the field.

Example:

{
    "first_name": {
        "value": "Berry",
        "evidence": [
            "Hi I am Berry and my full name is Berry Walsh."
        ]
    }
}

Only include evidence that directly supports the field.

Do not reuse evidence across unrelated fields.

Different fields may have different evidence.

Every non-unknown value must have supporting evidence.

If the value is unknown, return:

{
    "value": "unknown",
    "evidence": []
}

Output Format:

{
    "chat_response": [
        {
            "contact_type": {
                "value": "unknown",
                "evidence": []
            },

            "contact_role": {
                "value": "unknown",
                "evidence": []
            },

            "first_name": {
                "value": "unknown",
                "evidence": []
            },

            "last_name": {
                "value": "unknown",
                "evidence": []
            },

            "phone_number": {
                "value": "unknown",
                "evidence": []
            },

            "additional_phone_number": {
                "value": "unknown",
                "evidence": []
            },

            "email_address": {
                "value": "unknown",
                "evidence": []
            },

            "date_of_birth": {
                "value": "unknown",
                "evidence": []
            },

            "gender": {
                "value": "unknown",
                "evidence": []
            },

            "address": {
                "value": "unknown",
                "evidence": []
            },

            "street": {
                "value": "unknown",
                "evidence": []            
            },

            "city": {
                "value": "unknown",
                "evidence": []
            },

            "zip_postal_code": {
                "value": "unknown",
                "evidence": []
            },

            "state_province": {
                "value": "unknown",
                "evidence": []
            },

            "country": {
                "value": "unknown",
                "evidence": []
            }
        }
    ],
    "contact_confidence_score": "0%",
    "reported_verbatim": []
}

SOURCE INPUT OVERRIDE:
The input may be either a Chatqna conversation transcript OR free-text Notes. Treat the provided text as the only source of evidence. Do not assume it is always a bot/user transcript. For Notes, extract only information explicitly stated in the notes. Do not invent a bot/user exchange for Notes. The caller will ignore reported_verbatim from Notes and will preserve reported_verbatim only from the Chatqna extraction.
Return each unavailable field as the exact string "unknown" in this source-level extraction. The Python layer converts missing/unknown values to JSON null in the final comparison structure.
"""

def create_token_manager():
    """Create the existing Databricks OAuth token manager."""
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
        model_name=OPENAI_MODEL or "UNKNOWN",
    )


token_manager = create_token_manager()

# Reuse the HTTP connection between calls in this Python process.
# This does not change the API endpoint or authentication method.
http_session = requests.Session()


def empty_source_result():
    return {
        "chat_response": [],
        "contact_confidence_score": "0%",
        "reported_verbatim": [],
    }


def empty_final_result():
    return {
        "chat_response": [],
        "contact_confidence_score": "0%",
        "reported_verbatim": [],
    }


# Keep the original CONTACT_PROMPT unchanged. These final instructions define
# the combined two-source task and override only its source-level output format.
COMBINED_CONTACT_PROMPT = CONTACT_PROMPT + """

FINAL COMBINED TWO-SOURCE TASK (HIGHEST PRIORITY):

You will receive TWO separately labelled sources in the same user message:
1. CHATQNA: a bot/user conversation transcript.
2. NOTES: free-text notes.

Extract contacts independently from each source. Never use a value from one
source as evidence for the other source.

Then compare the Chatqna and Notes contact records by their order of first
appearance, matching record 1 with record 1, record 2 with record 2, and so on.
Do not merge two different people. Preserve the contact order from each source.
If a contact exists in only one source, still return that contact and use null
for the missing source candidate.

For every contact, return every field listed in CONTACT_FIELDS. Each field
must use this final comparison structure:

{
  "field_name": {
    "status": "confirm",
    "candidates": [
      {
        "value": "value or null",
        "source": "chatqna",
        "evidence": []
      },
      {
        "value": "value or null",
        "source": "notes",
        "evidence": []
      }
    ]
  }
}

COMPARISON RULES:
- Convert missing, blank, "unknown", "none", "null", "n/a" and "na" values
  into JSON null in candidates.
- If both source values are present and equal after case-insensitive,
  whitespace-normalized comparison, status is "confirm".
- For contact_role, compare the comma-separated roles without considering
  their order. Do not change the displayed role string.
- If both source values are present and differ, status is "conflict".
- If either source value is null, status is "confirm".
- Always include exactly two candidates in this order: chatqna, notes.
- Candidate evidence must be copied from the corresponding source only.
- Chatqna evidence must remain exact bot/user objects.
- Notes evidence must remain exact note text strings.
- If a candidate value is null, its evidence must be [].
- Do not invent evidence, values, contacts, or confirmation exchanges.
- Keep the original field extraction, contact classification, contact_role,
  email, name, address, DOB, and evidence rules above.

TOP-LEVEL OUTPUT:
Return valid JSON only, with exactly these keys:
{
  "chat_response": [],
  "contact_confidence_score": "0%",
  "reported_verbatim": []
}

- chat_response contains the compared contacts described above.
- contact_confidence_score must be based on the Chatqna extraction only and
  must be a percentage string.
- reported_verbatim must be taken from Chatqna only. Never include Notes
  content in reported_verbatim.
- If Chatqna is empty, return "0%" and [] for reported_verbatim.
- Do not return separate source-level extraction objects.
- Do not return explanations, markdown, or additional keys.
"""


def _clean_source_text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _clean_candidate_value(value):
    """Normalize unavailable values to JSON null."""
    if value is None:
        return None

    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.casefold() in {"", "unknown", "none", "null", "n/a", "na"}:
            return None
        return cleaned

    return value


def _safe_evidence(evidence, source_name, candidate_value):
    """Keep evidence in the required source-specific format."""
    if candidate_value is None or not isinstance(evidence, list):
        return []

    cleaned = []

    for item in evidence:
        if source_name == "chatqna":
            if isinstance(item, dict) and ("bot" in item or "user" in item):
                cleaned.append({
                    "bot": item.get("bot", "") or "",
                    "user": item.get("user", "") or "",
                })
        else:
            if isinstance(item, str) and item.strip():
                cleaned.append(item)

    return cleaned


def _normalize_final_response(result):
    """
    Validate and normalize the direct comparison JSON returned by the LLM.
    This function does not perform a second extraction or comparison.
    """
    if not isinstance(result, dict):
        return empty_final_result()

    raw_contacts = result.get("chat_response", [])
    if not isinstance(raw_contacts, list):
        raw_contacts = []

    normalized_contacts = []

    for raw_contact in raw_contacts:
        if not isinstance(raw_contact, dict):
            continue

        contact = {}

        for field in CONTACT_FIELDS:
            raw_field = raw_contact.get(field, {})
            if not isinstance(raw_field, dict):
                raw_field = {}

            status = raw_field.get("status", "confirm")
            if status not in {"confirm", "conflict"}:
                status = "confirm"

            raw_candidates = raw_field.get("candidates", [])
            if not isinstance(raw_candidates, list):
                raw_candidates = []

            # Map by source, so the final order is always stable.
            by_source = {}
            for candidate in raw_candidates:
                if isinstance(candidate, dict):
                    source_name = candidate.get("source")
                    if source_name in {"chatqna", "notes"}:
                        by_source[source_name] = candidate

            candidates = []
            for source_name in ("chatqna", "notes"):
                raw_candidate = by_source.get(source_name, {})
                value = _clean_candidate_value(raw_candidate.get("value"))
                evidence = _safe_evidence(
                    raw_candidate.get("evidence", []),
                    source_name,
                    value,
                )

                candidates.append({
                    "value": value,
                    "source": source_name,
                    "evidence": evidence,
                })

            # Recalculate status defensively from the final candidate values.
            chat_value = candidates[0]["value"]
            notes_value = candidates[1]["value"]

            if chat_value is not None and notes_value is not None:
                if field == "contact_role" and isinstance(chat_value, str) and isinstance(notes_value, str):
                    chat_key = tuple(sorted(
                        part.strip().casefold()
                        for part in chat_value.split(",")
                        if part.strip()
                    ))
                    notes_key = tuple(sorted(
                        part.strip().casefold()
                        for part in notes_value.split(",")
                        if part.strip()
                    ))
                elif isinstance(chat_value, str) and isinstance(notes_value, str):
                    chat_key = " ".join(chat_value.casefold().split())
                    notes_key = " ".join(notes_value.casefold().split())
                else:
                    chat_key = chat_value
                    notes_key = notes_value

                status = "confirm" if chat_key == notes_key else "conflict"
            else:
                status = "confirm"

            contact[field] = {
                "status": status,
                "candidates": candidates,
            }

        normalized_contacts.append(contact)

    confidence = result.get("contact_confidence_score", "0%")
    if confidence is None or str(confidence).strip() == "":
        confidence = "0%"
    confidence = str(confidence).strip()
    if not confidence.endswith("%"):
        confidence = f"{confidence}%"

    reported_verbatim = result.get("reported_verbatim", [])
    if not isinstance(reported_verbatim, list):
        reported_verbatim = []

    # Only retain Chatqna-style bot/user pairs in reported_verbatim.
    cleaned_verbatim = []
    for item in reported_verbatim:
        if isinstance(item, dict) and ("bot" in item or "user" in item):
            cleaned_verbatim.append({
                "bot": item.get("bot", "") or "",
                "user": item.get("user", "") or "",
            })

    return {
        "chat_response": normalized_contacts,
        "contact_confidence_score": confidence,
        "reported_verbatim": cleaned_verbatim,
    }


def _parse_json_response(content):
    """Parse JSON returned by the model, including fenced JSON responses."""
    if not content:
        return empty_final_result()

    content = content.strip()

    if content.startswith("```"):
        lines = content.splitlines()
        content = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        ).strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")

        if start < 0 or end <= start:
            logger.error("Contact Agent response did not contain valid JSON")
            return empty_final_result()

        try:
            parsed = json.loads(content[start:end + 1])
        except json.JSONDecodeError:
            logger.exception("Failed to parse Contact Agent JSON response")
            return empty_final_result()

    return _normalize_final_response(parsed)


def extract_contacts(chatqna, notes=""):
    """
    Extract and compare Chatqna + Notes in ONE Databricks LLM API request.

    Function signature and returned top-level keys remain compatible with
    the existing graph/supervisor integration.
    """
    total_start = time.perf_counter()

    chatqna_text = _clean_source_text(chatqna)
    notes_text = _clean_source_text(notes)

    logger.info(
        "CONTACT AGENT STARTED: single-call extraction. Chatqna chars=%d, Notes chars=%d",
        len(chatqna_text),
        len(notes_text),
    )

    if not chatqna_text and not notes_text:
        logger.info("Both Contact Agent sources are empty; skipping LLM call")
        return empty_final_result()

    token_start = time.perf_counter()
    access_token = token_manager.get_token()
    token_time = time.perf_counter() - token_start

    url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # JSON encoding keeps the two source boundaries explicit and safe.
    source_payload = {
        "CHATQNA": chatqna_text,
        "NOTES": notes_text,
    }

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": COMBINED_CONTACT_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    "Extract and compare contacts from these two independent sources. "
                    "Follow the final combined two-source instructions. "
                    "Source content (JSON):\n"
                    + json.dumps(source_payload, ensure_ascii=False)
                ),
            },
        ],
    }

    api_start = time.perf_counter()

    try:
        response = http_session.post(
            url,
            headers=headers,
            json=payload,
            timeout=(10, 120),
        )
        api_time = time.perf_counter() - api_start

        logger.info(
            "Contact Agent single API call completed: status=%s, api_time=%.2fs, token_time=%.2fs",
            response.status_code,
            api_time,
            token_time,
        )

        response.raise_for_status()
        response_data = response.json()

        choices = response_data.get("choices", [])
        if not choices:
            logger.error("Contact Agent response contains no choices")
            result = empty_final_result()
        else:
            message = choices[0].get("message", {})
            result = _parse_json_response(message.get("content", ""))

    except requests.Timeout:
        logger.exception("Contact Agent API request timed out")
        result = empty_final_result()

    except requests.RequestException:
        logger.exception("Contact Agent API request failed")
        result = empty_final_result()

    except Exception:
        logger.exception("Unexpected Contact Agent failure")
        result = empty_final_result()

    total_time = time.perf_counter() - total_start

    logger.info(
        "CONTACT AGENT EXECUTION TIME: %.2f seconds (token=%.2fs, api=%.2fs)",
        total_time,
        token_time,
        time.perf_counter() - api_start if "api_start" in locals() else 0.0,
    )
    logger.info(
        "CONTACT AGENT COMPLETED: compared_contacts=%d",
        len(result.get("chat_response", [])),
    )

    return result
