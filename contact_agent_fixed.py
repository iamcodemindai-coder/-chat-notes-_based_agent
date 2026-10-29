import re
import json
import logging
import os
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from oauth_token_manager_2 import DatabricksTokenManager

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


Output Format:

{
    "chat_response": [
        {
            "contact_type": "unknown",
            "contact_role": "unknown",
            "first_name": "Other",
            "last_name": "unknown",
            "phone_number": "unknown",
            "additional_phone_number": "unknown",
            "email_address": "unknown",
            "date_of_birth": "MM/DD/YY",
            "gender": "unknown",
            "address": "unknown",
            "street": "unknown",
            "city": "unknown",
            "zip_postal_code": "unknown",
            "state_province": "unknown",
            "country": "unknown"
        }
    ],
    "contact_confidence_score": "0%",
    "reported_verbatim": [
        {
            "bot": "",
            "user": ""
        }
    ]
}

SOURCE INPUT OVERRIDE:
The input may be either a Chatqna conversation transcript OR free-text Notes. Treat the provided text as the only source of evidence. Do not assume it is always a bot/user transcript. For Notes, extract only information explicitly stated in the notes. Do not invent a bot/user exchange for Notes. The caller will ignore reported_verbatim from Notes and will preserve reported_verbatim only from the Chatqna extraction.
Return each unavailable field as the exact string "unknown" in this source-level extraction. The Python layer converts missing/unknown values to JSON null in the final comparison structure.
"""


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
        model_name=OPENAI_MODEL or "UNKNOWN",
    )


token_manager = create_token_manager()


def empty_source_result():
    return {
        "chat_response": [],
        "contact_confidence_score": 0,
        "reported_verbatim": [],
    }


def parse_json_response(content):
    """Parse the JSON returned by the extraction model safely."""
    if not content:
        return empty_source_result()

    content = content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        content = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        ).strip()

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end <= start:
            logger.error("Contact Agent response did not contain valid JSON")
            return empty_source_result()
        try:
            result = json.loads(content[start:end + 1])
        except json.JSONDecodeError:
            logger.exception("Failed to parse Contact Agent response as JSON")
            return empty_source_result()

    if not isinstance(result, dict):
        return empty_source_result()

    result.setdefault("chat_response", [])
    result.setdefault("contact_confidence_score", 0)
    result.setdefault("reported_verbatim", [])
    if not isinstance(result["chat_response"], list):
        result["chat_response"] = []
    if not isinstance(result["reported_verbatim"], list):
        result["reported_verbatim"] = []
    return result


def _extract_one_source(source_text, source_name):
    """Run the existing contact extraction prompt on one source independently."""
    if source_text is None:
        source_text = ""
    if not isinstance(source_text, str):
        source_text = str(source_text)
    if not source_text.strip():
        logger.info("Contact Agent received empty %s source", source_name)
        return empty_source_result()

    access_token = token_manager.get_token()
    url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": CONTACT_PROMPT},
            {
                "role": "user",
                "content": (
                    f"SOURCE NAME: {source_name}\n"
                    "Extract contact records only from the source text below. "
                    "Do not use information from any other source. "
                    "If SOURCE NAME is notes, return reported_verbatim as an empty array.\n\n"
                    "SOURCE TEXT START\n"
                    f"{source_text}"
                    "\nSOURCE TEXT END"
                ),
            },
        ],
    }

    logger.info("Calling Databricks Chat Completions API for %s", source_name)
    response = requests.post(url, headers=headers, json=payload, timeout=120)
    logger.info("Contact Agent %s API status=%s", source_name, response.status_code)
    response.raise_for_status()

    response_data = response.json()
    choices = response_data.get("choices", [])
    if not choices:
        logger.error("Contact Agent %s response contains no choices", source_name)
        return empty_source_result()

    message = choices[0].get("message", {})
    return parse_json_response(message.get("content", ""))


def _map_chatqna_verbatim_to_fields(chatqna_result):
    """Attach original, non-empty Chatqna verbatim entries to matching fields.

    Use the original conversation objects directly instead of asking another
    LLM to return indexes. This avoids attaching empty bot/user objects.
    """
    contacts = _get_contact_records(chatqna_result)
    verbatim = chatqna_result.get("reported_verbatim", [])

    if not contacts or not isinstance(verbatim, list) or not verbatim:
        return [{} for _ in contacts]

    def text_of(item):
        if not isinstance(item, dict):
            return ""
        return " ".join(
            str(item.get(key) or "").strip()
            for key in ("bot", "user")
            if str(item.get(key) or "").strip()
        )

    def compact(value):
        return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())

    valid_entries = [
        (item, text_of(item)) for item in verbatim
        if isinstance(item, dict) and text_of(item)
    ]
    results = []

    for contact in contacts:
        field_evidence = {}
        for field in CONTACT_FIELDS:
            value = _clean_value(contact.get(field))
            matched = []

            if value is not None:
                value_text = str(value).strip()
                value_compact = compact(value_text)
                value_digits = re.sub(r"\D", "", value_text)
                role_aliases = {
                    "hcp": ("healthcareprovider", "healthcareprofessional", "hcp"),
                    "healthcareprovider": ("healthcareprovider", "healthcareprofessional", "hcp"),
                    "healthcareprofessional": ("healthcareprovider", "healthcareprofessional", "hcp"),
                    "patient": ("patient",),
                    "both": ("healthcareprovider", "healthcareprofessional", "hcp", "patient"),
                }
                targets = role_aliases.get(value_compact, (value_compact,)) if field == "contact_role" else (value_compact,)

                for item, conversation_text in valid_entries:
                    conversation_compact = compact(conversation_text)
                    is_match = bool(value_compact) and any(
                        target and target in conversation_compact for target in targets
                    )

                    if (not is_match and field in {"phone", "phone_number", "mobile", "mobile_number"}
                            and value_digits):
                        conversation_digits = re.sub(r"\D", "", conversation_text)
                        is_match = value_digits in conversation_digits

                    if not is_match and any(token in field for token in ("address", "city", "state", "zip", "postal")):
                        words = [compact(word) for word in re.findall(r"[A-Za-z0-9]+", value_text)
                                 if len(compact(word)) >= 3]
                        if words:
                            hits = sum(1 for word in words if word in conversation_compact)
                            is_match = hits >= min(2, len(words))

                    if is_match:
                        matched.append(item)

            field_evidence[field] = matched
        results.append(field_evidence)

    return results

def _clean_value(value):
    """Convert absent/unknown source values to None; preserve actual values."""
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.lower() in {"", "unknown", "none", "null", "n/a", "na"}:
            return None
        return cleaned
    return value

# -------------------------------------------------------------------------------------------------------------------------
# ------------------------------------------BELOW CODE USED FOR ALL STRING IN THE OUTPUT-----------------------------------
# -------------------------------------------------------------------------------------------------------------------------
# def _comparison_key(value):
#     """Normalize values only for comparison; never modify the displayed value."""
#     if isinstance(value, str):
#         return " ".join(value.strip().casefold().split())
#     return value

# --------------------------------------------------------------------------------------------------------------------------
# ------------------------------------------BELOW CODE USED FOR ALL STRING AND SPECIALLY FOR CONTACT_ROLE-------------------
# --------------------------------------------------------------------------------------------------------------------------
def _comparison_key(value, field=None):
    """Normalize values only for comparison; never modify displayed values."""
    if not isinstance(value, str):
        return value

    normalized = " ".join(value.strip().casefold().split())

    if field == "contact_role":
        return tuple(sorted(
            role.strip()
            for role in normalized.split(",")
            if role.strip()
        ))

    return normalized

def _get_contact_records(result):
    records = result.get("chat_response", []) if isinstance(result, dict) else []
    return records if isinstance(records, list) else []


def _build_compared_contacts(chatqna_result, notes_result, chatqna_field_verbatim=None):
    """Compare matching contact records by order, then compare every field."""
    chat_contacts = _get_contact_records(chatqna_result)
    notes_contacts = _get_contact_records(notes_result)
    chatqna_field_verbatim = chatqna_field_verbatim or []
    count = max(len(chat_contacts), len(notes_contacts), 1)
    compared = []

    for index in range(count):
        chat_contact = chat_contacts[index] if index < len(chat_contacts) and isinstance(chat_contacts[index], dict) else {}
        notes_contact = notes_contacts[index] if index < len(notes_contacts) and isinstance(notes_contacts[index], dict) else {}
        compared_contact = {}

        for field in CONTACT_FIELDS:
            chat_value = _clean_value(chat_contact.get(field))
            notes_value = _clean_value(notes_contact.get(field))

            if chat_value is not None and notes_value is not None:
                #----------------- I CHANGED BELOW LINE DUE TO CONTACT_ROLE "," SEPARATION ------------------------------
                #status = "confirm" if _comparison_key(chat_value) == _comparison_key(notes_value) else "conflict"
                status = "confirm" if _comparison_key(chat_value, field) == _comparison_key(notes_value, field) else "conflict"
            else:
                status = "confirm"

            field_verbatim = []
            if index < len(chatqna_field_verbatim):
                contact_evidence = chatqna_field_verbatim[index]
                if isinstance(contact_evidence, dict):
                    evidence = contact_evidence.get(field, [])
                    if isinstance(evidence, list) and chat_value is not None:
                        field_verbatim = evidence

            compared_contact[field] = {
                "status": status,
                "candidates": [
                    {field: chat_value, "source": "chatqna", "verbatim": field_verbatim},
                    {field: notes_value, "source": "notes"},
                ],
            }
        compared.append(compared_contact)

    return compared


def extract_contacts(chatqna, notes=""):
    """Extract contacts independently from Chatqna and Notes, then compare fields.

    The first argument remains Chatqna for compatibility with the existing caller.
    """
    logger.info("CONTACT AGENT STARTED: independent Chatqna and Notes extraction")

    try:
        chatqna_result = _extract_one_source(chatqna, "chatqna")
    except Exception:
        logger.exception("Contact extraction failed for Chatqna")
        chatqna_result = empty_source_result()

    try:
        notes_result = _extract_one_source(notes, "notes")
    except Exception:
        logger.exception("Contact extraction failed for Notes")
        notes_result = empty_source_result()

    # Map the existing Chatqna verbatim entries to fields without changing the
    # original top-level reported_verbatim returned by the Contact Agent.
    chatqna_field_verbatim = _map_chatqna_verbatim_to_fields(chatqna_result)
    compared_contacts = _build_compared_contacts(
        chatqna_result,
        notes_result,
        chatqna_field_verbatim,
    )

    # Keep the existing Chatqna reported-verbatim and confidence values unchanged.
    result = {
        "chat_response": compared_contacts,
        "contact_confidence_score": chatqna_result.get("contact_confidence_score", 0),
        "reported_verbatim": chatqna_result.get("reported_verbatim", []),
    }
    logger.info(
        "CONTACT AGENT COMPLETED: chatqna_contacts=%d notes_contacts=%d compared_contacts=%d",
        len(_get_contact_records(chatqna_result)),
        len(_get_contact_records(notes_result)),
        len(compared_contacts),
    )
    return result
