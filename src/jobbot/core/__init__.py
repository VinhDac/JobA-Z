"""Core — the shared backbone every module sits on.

Lives here:
    - Shared data types: Job, Proposal, Application, AuditEntry
    - SQLite store + the 4 layers raw / derived / state / audit
    - Cache (never fetch twice, never score twice)
    - The proposal queue and the Yes/No gate
    - Executing a proposal once it has been approved

Does NOT live here:
    - Anything specific to one source (-> ingest/)
    - Scoring rules (-> scoring/)
    - Anything that knows what LinkedIn/Greenhouse/... is
"""
