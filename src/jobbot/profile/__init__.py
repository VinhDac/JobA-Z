"""M0 — The user profile.  WITHOUT IT NO MODULE WORKS CORRECTLY.

This is the OPENING step. Before a single posting is fetched, the system has
to know who the user is and what they want. Without it:
    ingest   pulls in irrelevant postings
    scoring  scores against thin air
    cv       has no material to write from
    mail     has no name, address or signature
    outreach does not know who it is representing

Here:
    - Questions grouped by WHO USES THEM: muc_tieu / rang_buoc / nang_luc /
      danh_tinh / project
    - Only 2 required: job_titles + markets. The rest fills in over time.
    - Ask what ingest CAN USE: real job titles, not a taxonomy
    - The raw material: CV, experience, projects, skills
    - What they want: role, band, market, salary, limits
    - Constraints: what they will NOT take (the most commonly forgotten part)
    - Stored per version. A profile changes over time.

The rule: a profile is LIVING data, not a form filled in once.
After 50 rejections what someone wants is different. The system has to spot
the gaps and propose asking again — through the same Yes/No queue as every
other module (design.md §1).

NOT here:
    - Match scoring (-> scoring/)
    - Building the CV file (-> cv/)
"""
