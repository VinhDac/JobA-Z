"""The app's pages. One file per page.

A page ONLY DRAWS: take data, return HTML. It never reads the DB and decides
nothing. The data comes from dashboard/live.py — which reads the real DB;
there is no mock layer any more.

Tabs WITH RUNNING TIME (search, score) share the runtime.py frame:
what is running · their own journal · statistics · charts · settings · debug.
"""
