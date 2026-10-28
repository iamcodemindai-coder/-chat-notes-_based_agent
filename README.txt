UPDATED CONTACT + NOTES POC FILES

Changed files included:
- contact_agent.py: independently extracts from Chatqna and Notes, then compares the 15 contact fields.
- supervisor.py: preserves the nested field status/candidates output rather than flattening it.
- graph.py: passes both sources to Contact Agent; Consent Agent still receives Chatqna only.
- main.py: logs Notes length and retains the /ccai API contract.
- test.py: local graph test supports Notes.
- input.json: sample input.

Keep your existing consent_agent.py, state.py, logging_config.py, oauth_token_manager_2.py, and .env unchanged.
Run locally: python test.py
Run API: python main.py
Health check: GET /
POST endpoint: /ccai

Important behavior:
- MasterCaseId and AutomationReportId are copied directly from the input.
- Missing contact values become JSON null inside candidates.
- status is conflict only when both sources contain values and those values differ; otherwise it is confirm.
- Comparisons ignore case and repeated whitespace, while candidate values preserve the extracted text.
- Contact confidence and reported_verbatim are retained from the Chatqna extraction.
- Contact records are paired by their order of appearance in each source. If the sources list multiple people in different orders, review this matching rule during POC testing.
