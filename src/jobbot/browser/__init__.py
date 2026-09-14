"""Driving Chrome — for the sources with no API.

Why a hand-written WebSocket client instead of installing Playwright: this
whole project installs nothing and runs on the Python already on the machine.
What a job board needs is very simple — open a page, wait, take the HTML,
scroll, click — so ~120 lines is enough.

If a page later turns out to be too complex, Playwright is one pip away and
the interface in `cdp.py` does not have to change.
"""
