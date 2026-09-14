"""Settings — a MENU, not a tab.

It returns an HTML FRAGMENT, not a whole page: live.js loads it into the
overlay when the cog is pressed. Made a tab, it would take a place in the
sidebar alongside Search and Projects — while it is not a job, it is a few
switches you open, adjust and close.

Two knobs only. The measure for letting something in here:

    1. it has more than one right answer
    2. THE USER is the one who should choose
    3. changing it makes the machine behave differently

Miss any of the three and it is something else: one right answer -> that is A
BUG, fix the code; the machine reporting on itself -> that is A READOUT;
deliberately unchangeable -> that is A SAFETY BOUNDARY. The old page had 18
rows and only 2 passed this measure.

Neither knob touches any verdict — changing them only changes how it runs,
from the next scan onwards. What changes a verdict lives in the Sieve panel on
the Search tab, where the Apply button states how many postings will be
re-judged.

THREE TABS. It used to be one 782px column inside a 660px box — the "Start
over" section sat below the fold, reachable only by scrolling, and nobody knew
it could be scrolled. Split into tabs, each tab fits one screen and the box
shrinks to an actual dialog instead of a column running most of the window's
height.

Split BY JOB, not by length: what can be changed / what is only read / what
destroys. Leaving the destructive thing on the same screen as the scan
interval means sooner or later somebody presses it by mistake.

DRAWING ONLY.
"""

from __future__ import annotations

from html import escape as esc

def _num(name: str, value: int, low: int, high: int, unit: str) -> str:
    return (f"<input type=number name={name} value='{value}'"
            f" min={low} max={high} step=1><span class=unit>{esc(unit)}</span>")


PACE_TEXT = [
    ("nhe", "Gentle", "4-7 seconds per posting · least likely to be throttled"),
    ("thuong", "Normal", "2.5-5 seconds · the default"),
    ("nhanh", "Fast", "1.2-2.5 seconds · twice the call density, easier to throttle"),
]


def _nhip(pace: str) -> str:
    """The scan loop's REAL performance knob — and it is a TRADE-OFF knob.

    Why it is not "how many tabs in parallel": N tabs at pace P is identical
    to 1 tab at pace P/N — the same calls per second, the same throttling
    risk. Parallelism is only a more complicated way of writing a smaller
    number, plus N Chrome windows eating RAM and N places to die halfway. So
    what is put on screen is the thing that actually changes: the pace.

    STATE THE TRADE right on the screen. A knob reading "Fast" that does not
    say what fast costs is a knob inviting people to press it and take the
    consequences.
    """
    nut = "".join(
        f"<label class=prow><input type=radio name=pace value='{esc(v)}'"
        f"{' checked' if v == pace else ''}>"
        f"<b>{esc(ten)}</b><span class=muted>{esc(ghi)}</span></label>"
        for v, ten, ghi in PACE_TEXT)
    return (f"<div class=sthead>LinkedIn call pace</div>{nut}"
            "<div class=safe>Company boards do not touch this pace — they are "
            "public APIs, one call per board. The pace applies only to "
            "LinkedIn, the one place the app is a guest.</div>")


def _nguon(sources: list[dict], board_on: bool) -> str:
    """Turn each ATS on or off. THREE of them, not 34.

    "API" here means three ATS providers, not 34 company boards. Introducing
    each company would be meaningless ("Jane Street — a fund"), while the
    three ATS really do differ: different data shapes, different kinds of
    company, very different usable rates.

    Introduced with THIS STORE's REAL NUMBERS, not adjectives. "Modern",
    "popular" lets nobody choose anything; "600 postings, 6 kept" lets them
    choose at once.
    """
    hang = ""
    for n in sources:
        hang += (
            f"<label class='prow srcline{'' if n['on'] else ' off'}'>"
            f"<input type=checkbox name=ats value='{esc(n['id'])}'"
            f"{' checked' if n['on'] else ''}>"
            f"<b>{esc(n['ten'])}</b>"
            f"<span class=muted>{esc(n['note'])}</span>"
            f"<span class=srcnum>"
            + (f"{n['boards']} boards · " if n["boards"] else "")
            + f"{n['tin']:,} postings in · {n['giu']:,} kept"
            + (f" · {n['remote']:,} say remote" if n["remote"] else "")
            + "</span></label>")
    # While the BIG switch is off, the small ones have no effect. Without
    # saying so, the user toggles things here and then waits for something
    # that never comes.
    canh = ("" if board_on else
            "<div class=safe><b>Boards are OFF</b> in Adjust · Search — the "
            "switches below have no effect until they are turned back on.</div>")
    return (
        "<form class=setform method=post action='/settings'>"
        "<input type=hidden name=phan value=nguon>"
        + canh +
        "<div class=sthead>Fast sources</div>"
        "<div class=safe>Three ATS providers, plus the LinkedIn job alert "
        "emails in the mailbox. Untick one and the next scan stops calling it "
        "— the postings already fetched stay in the store.</div>"
        + hang +
        "<div class=setfoot>"
        "<button class='mbtn apply' type=submit>Save</button>"
        "<span class=applynote>takes effect from the next scan · deletes "
        "nothing already fetched</span></div>"
        "</form>")


def _gmail(ready: bool, address: str, days: int, ho_so: str = "") -> str:
    """Connect the mailbox + how many days to reread. NEVER draws the password.

    This used to sit at the head of the Track tab — the page Vin opens daily.
    It is CONFIGURATION: connected once and then done, so its place is
    Settings. What stayed on Track is THE WORK: the Scan mail button.

    Even here, only THE ADDRESS and THE STATE are drawn. A password field with
    a value is a password sitting in the HTML — readable via View Source and
    cached by the browser. The real value lives in config.toml (chmod 600,
    gitignored).
    """
    ngay = (
        "<form class=setform method=post action='/settings'>"
        "<input type=hidden name=phan value=gmail>"
        "<div class=sthead>How many days of mail to reread</div>"
        "<label class=srow><span>Each scan rereads</span>"
        + _num("mail_days", days, 1, 365, "days") + "</label>"
        "<div class=safe>A reply to an application sent last month still has "
        "to be caught, so 30 days is the default. Set it shorter and scans are "
        "quicker but late replies are missed.</div>"
        "<div class=setfoot>"
        "<button class='mbtn apply' type=submit>Save</button>"
        "<span class=applynote>takes effect from the next mail scan</span></div>"
        "</form>")

    if ready:
        # "saved", NOT "connected": all this place knows is that the config
        # HAS a string, not whether that string can still log in. Have Google
        # revoke the app password and this line stays green, and Vin believes
        # the mailbox is running.
        # NO delete button here. It is connected once and done; the only way
        # to remove it is "Start over" on the other tab. To change it, paste
        # the new password over the old.
        noi = (f"<div class=safe>Mailbox <b>{esc(address)}</b> saved — go to "
               f"the Track tab and press Scan mail to check it can still log "
               f"in.<br>Connecting is a one-off: the password only goes when "
               f"you press <b>Start over</b>. To change it, paste a new "
               f"password over the top."
               f"</div>"
               f"<form class=boxform data-post='/api/mail/setup'>"
               f"<input name=address type=email value='{esc(address)}'"
               f" placeholder='job mailbox address' required>"
               "<input name=password type=password autocomplete=off"
               " placeholder='paste a new app password to change it' required>"
               "<button class='mbtn apply' type=submit>Change</button>"
               "<span class=formnote></span></form>")
    else:
        noi = (
            "<form class=boxform data-post='/api/mail/setup'>"
            f"<input name=address type=email value='{esc(address)}'"
            f" placeholder='job mailbox address' required>"
            "<input name=password type=password autocomplete=off"
            " placeholder='16-character app password' required>"
            "<button class='mbtn apply' type=submit>Connect</button>"
            "<div class=boxwhy>Get one at <code>myaccount.google.com/apppasswords</code>"
            " (turn on 2-step verification first). NOT the account password —"
            " Gmail cut off IMAP with account passwords back in 2022. The app"
            " password is stored in <code>config/config.toml</code>, chmod 600,"
            " gitignored.<span class=formnote></span></div></form>")

    # Say UP FRONT that it has to match, rather than reporting a failure after
    # Connect is pressed. And prefill the profile address: making someone
    # retype an address already known is inviting a typo.
    khop = (f"<div class=safe>It has to be the address declared in the profile "
            f"— <b>{esc(ho_so)}</b>. That is the address printed on the CV and "
            f"filled into applications, i.e. the one employers press Reply to; "
            f"connect a different mailbox and the app watches one place while "
            f"the mail arrives at another.</div>"
            if ho_so else
            "<div class=safe>The profile has no contact address yet — fill it "
            "in on the Profile tab first, then connect that same mailbox.</div>")
    return (f"<div class=sthead>Job mailbox</div>"
            f"<div class=safe>Incoming mail is what updates the Track table by "
            f"itself — replies, interview invitations, rejections.</div>"
            f"{khop}{noi}{ngay}")


def _chung(mau_nay: str, tu_truc: bool) -> str:
    """The GENERAL tab — settings for THE WHOLE APP, belonging to no stage.

    The boundary with the other tabs: "Run" sets the scan pace, "Sources" sets
    where it looks, "Gmail" sets the mailbox — all three configure ONE job.
    Here is what holds on every tab: the colour, and whether the app goes on
    watch by itself when it opens.

    Pressing takes effect AT ONCE, with no Save button. A colour that needs
    Save before it shows leaves the user unable to compare two colours — and
    comparing is how people choose.
    """
    from .. import mau as _mau
    o = ""
    for ma, (ten, bo) in _mau.BANG.items():
        on = ma == mau_nay
        o += (f"<button class='swatch{' on' if on else ''}'"
              f" data-post='/api/chung' data-arg='mau:{ma}'"
              f" title='{esc(ten)}' style='--o:{bo['--acc']}'>"
              f"<span class=swdot></span><b>{esc(ten)}</b>"
              + ("<i>in use</i>" if on else "") + "</button>")
    truc = (f"<div class='swrow{'' if tu_truc else ' off'}'>"
            f"<button class='mbtn tiny swbtn{'' if tu_truc else ' off'}'"
            f" data-post='/api/chung' data-arg='truc:"
            f"{'0' if tu_truc else '1'}'>{'ON' if tu_truc else 'OFF'}</button>"
            f"<b class=swten>Go on watch when the app opens</b>"
            f"<span class=swnow>"
            + ("runs sessions on schedule straight away" if tu_truc
               else "waits for you to press")
            + "</span><details class=swwhy><summary>why</summary>"
            "<div class=swbody>OFF by default, deliberately: opening the app "
            "and having it open Chrome and start scanning before you have even "
            "looked at anything is wrong. Turn it on once you are comfortable "
            "with the configuration. The Start session button on the Overview "
            "tab turns this on too.</div></details></div>")
    return ("<div class=sthead>System colour</div>"
            f"<div class=swgrid>{o}</div>"
            "<div class=note>Changing the colour does NOT touch the colours "
            "that carry meaning: red is still rejected, orange is still a "
            "warning, blue is still background. Only the ACCENT changes — what "
            "marks «what is selected» and «what has to be done».</div>"
            "<div class=sthead>When the app opens</div>" + truc)


def _thong_bao(noi: bool, token_che: str, chat: str, bat: dict,
               muc: str, nguong: int, gio: int, tin_test: tuple = ()) -> str:
    """The NOTIFICATIONS tab — messages to your phone, and remote control.

    NEVER DRAW THE TOKEN. A field with a value is a secret sitting in the
    HTML: readable via View Source and cached by the browser. Only the last
    four characters are shown, so the user knows which one they pasted.
    """
    from ...core import prefs, tele

    # "CONNECTED" here only means BOTH STRINGS ARE PRESENT in the config, not
    # that they are right. Have the token revoked and this line stays green —
    # so it has to invite a Test rather than claim "working".
    buoc = ("1. On Telegram, message <b>@BotFather</b> → <b>/newbot</b>. It "
            "returns a token like <b>7123456789:AAH…</b> — copy the WHOLE "
            "line.<br>"
            "2. Open the bot you just made and send it <b>/start</b>.<br>"
            "3. Paste the token in the field below and press <b>Save</b> — the "
            "machine works out the rest.<br>"
            "4. Press <b>Test</b>: a test message arrives on your phone.")
    if noi:
        dau = (f"<div class=safe>Connected · token <b>{esc(token_che)}</b> — "
               f"but <i>saved</i> is not necessarily <i>right</i> (revoke the "
               f"token and this line stays green). Press <b>Test</b> to know "
               f"for certain.<br><br>{buoc}</div>")
    else:
        dau = ("<div class=safe><b>Not connected.</b> With the machine left "
               "running at home, nobody sees a macOS notification — Telegram "
               "is the only route that does not mean opening a router "
               f"port.<br><br>{buoc}</div>")

    form = (
        "<form class=setform method=post action='/settings'>"
        "<input type=hidden name=phan value=telegram>"
        "<label class=srow><span>Bot token</span>"
        "<input class=stext type=password name=token autocomplete=off"
        " placeholder='paste the token from @BotFather'></label>"
        # NO CHAT ID FIELD. The chat id is something the machine can read from
        # Telegram itself; asking the user is asking a question they have no
        # way to answer — and that field led straight to people pasting their
        # phone number in. A field carrying no new information is just a place
        # to get it wrong.
        "<div class=setfoot>"
        "<button class='mbtn apply' type=submit>Save</button>"
        # THE TEST BUTTON really sends a message. Checking each link and then
        # concluding "it probably works" is exactly the self-deception this app
        # avoids — the whole chain token → chat id → network → Telegram can
        # only be proved by going all the way round it.
        "<button class=mbtn type=submit name=test value=1"
        " title='Send a test message to your phone — it also says which mode"
        " you are in and which commands you can use'>Test</button>"
        "<span class=applynote>the token lives only in config.toml (chmod 600, "
        "gitignored) — never in the DB, never in the journal</span></div>"
        "</form>")

    # THE TEST RESULT goes right at the top, not hidden in the journal: the
    # person who just pressed it is looking here, and on failure it has to say
    # WHERE it failed rather than "could not send" — they knew that already.
    if tin_test:
        was_ok, cau = tin_test
        # NO esc() HERE: this sentence is composed by bao.py, which already
        # escapes every fragment taken from Telegram with tele.thoat() before
        # joining. Escaping again prints <b> as literal text — the user reads
        # "&lt;b&gt;" in the middle of the instructions.
        #
        # The heading is GENERAL, because the same banner reports all three
        # jobs: saving, finding the chat id, and sending the test. Writing
        # "Sent" for a Save would be wrong.
        form = (f"<div class='testkq {'ok' if was_ok else 'xau'}'>"
                f"<b>{'✅ That worked' if was_ok else '⚠️ Not yet'}</b>"
                f"<span>{cau}</span></div>") + form

    # --- the four kinds of message
    hang = ""
    for khoa, (ten, y) in prefs.BAO.items():
        on = bool(bat.get(khoa))
        hang += (f"<div class='swrow{'' if on else ' off'}'>"
                 f"<button class='mbtn tiny swbtn{'' if on else ' off'}'"
                 f" data-post='/api/bao' data-arg='{esc(khoa)}:"
                 f"{'0' if on else '1'}'>{'ON' if on else 'OFF'}</button>"
                 f"<b class=swten>{esc(ten)}</b>"
                 f"<span class=swnow>{'messages' if on else 'skipped'}</span>"
                 f"<details class=swwhy><summary>why</summary>"
                 f"<div class=swbody>{esc(y)}</div></details></div>")

    # --- the three control levels
    nut = ""
    for ma, (ten, y) in tele.MUC_DIEU_KHIEN.items():
        on = ma == muc
        nut += (f"<button class='mbtn tiny{' on' if on else ' off'}'"
                f" data-post='/api/bao' data-arg='muc:{esc(ma)}'"
                f" title='{esc(y)}'>{'✓ ' if on else ''}{esc(ten)}</button>")
    y_muc = tele.MUC_DIEU_KHIEN.get(muc, ("", ""))[1]

    so = ("<form class=setform method=post action='/settings'>"
          "<input type=hidden name=phan value=bao_so>"
          "<label class=srow><span>Queue piled up past</span>"
          + _num("bao_nguong", nguong, 1, 999, "items") + "</label>"
          "<label class=srow><span>Send the end-of-day report at</span>"
          + _num("bao_gio", gio, 0, 23, "o'clock") + "</label>"
          "<div class=setfoot><button class='mbtn apply' type=submit>Save"
          "</button></div></form>")

    return (dau + form
            + "<div class=sthead>When to message your phone</div>" + hang + so
            + "<div class=sthead>Remote control</div>"
            + f"<div class=srcrow>{nut}</div>"
            + f"<div class=note>{esc(y_muc)}</div>"
            + "<div class=safe><b>Three hard latches, not changeable here:</b> "
              "commands are only accepted from the one pinned chat id — a "
              "message from any other chat is dropped and journalled. The "
              "token never reaches the DB or the journal. And there is "
              "<b>no apply command at any level</b>: pressing Submit is still "
              "yours, in front of the form.</div>")


def render(*, every: int, hours: tuple[int, int],
           status: list[tuple[str, str]], pace: str = "thuong",
           sources: list[dict] | None = None, board_on: bool = True,
           mail_ready: bool = False, mail_address: str = "", mail_days: int = 30,
           mail_profile: str = "",
           reset_rows: int = 0, reset_files: int = 0, reset_mb: float = 0.0,
           reset_backup_dir: str = "",
           mau_nay: str = "la", tu_truc: bool = False,
           tele_noi: bool = False, tele_token: str = "", tele_chat: str = "",
           bao_bat: dict | None = None, bao_muc: str = "tat",
           bao_nguong: int = 10, bao_gio: int = 20,
           tin_test: tuple = (), mo: str = "") -> str:
    rows = "".join(f"<div class=strow><span>{esc(k)}</span><b>{esc(v)}</b></div>"
                   for k, v in status)

    chay = (
        "<form class=setform method=post action='/settings'>"
        "<input type=hidden name=phan value=chay>"
        "<label class=srow><span>Rescan every</span>"
        + _num("every", every, 5, 1440, "minutes") + "</label>"
        "<label class=srow><span>Chrome runs from</span>"
        + _num("from", hours[0], 0, 23, "o'clock") + "</label>"
        "<label class=srow><span>… until</span>"
        + _num("to", hours[1], 1, 24, "o'clock") + "</label>"
        + _nhip(pace) +
        "<div class=setfoot>"
        "<button class='mbtn apply' type=submit>Save</button>"
        "<span class=applynote>takes effect from the next scan · touches "
        "neither the scores nor the filters</span></div>"
        "</form>")

    # Numbers the machine reports about itself — NOT settings, so they get a
    # tab of their own that says it is read-only. The safety boundaries sit
    # here too because they are equally unchangeable; only the promises WITH A
    # TEST BEHIND THEM are kept (see tests/test_browser.py) — a promise nobody
    # checks rots without anyone noticing.
    tinh_trang = (
        f"<div class=stlist>{rows}</div>"
        "<div class=sthead>Boundaries — not changeable</div>"
        "<div class=safe>Chrome runs on a profile of its own, logged into no "
        "account, reading only public careers pages. On cookies it only presses "
        "Reject. Blocked, it stops and journals it rather than arguing.</div>")

    # GENERAL GOES FIRST: it is the whole app's settings, the later tabs belong
    # to individual stages.
    tab = [("chung", "General", _chung(mau_nay, tu_truc)),
           ("bao", "Notifications",
            _thong_bao(tele_noi, tele_token, tele_chat, bao_bat or {},
                       bao_muc, bao_nguong, bao_gio, tin_test)),
           ("chay", "Run", chay),
           ("nguon", "Sources", _nguon(sources or [], board_on)),
           ("gmail", "Gmail",
            _gmail(mail_ready, mail_address or mail_profile, mail_days,
                   mail_profile)),
           ("xem", "Status", tinh_trang),
           ("lam-lai", "Start over",
            _lam_lai(reset_rows, reset_files, reset_mb, reset_backup_dir))]

    # WHICH TAB OPENS. `mo` = the tab a form was just submitted from, so that
    # after Save the user stays exactly where they were standing.
    #
    # Without it every POST lands back on the first tab — press Test and the
    # result banner is on the Notifications tab while the screen is showing
    # General: to the user it looks as if nothing happened.
    co = {tid for tid, _t, _n in tab}
    dau = mo if mo in co else tab[0][0]
    # SINGLE QUOTES INSIDE AN f-string, never nested double quotes.
    #
    # A previous version wrote f"...{" on" if ... else ""}..." — double quotes
    # nested inside double quotes. That is PEP 701, valid only FROM Python
    # 3.12; on 3.9 (the version macOS ships) and 3.11 (the version the README
    # claims) the WHOLE FILE fails to compile, meaning opening the Settings tab
    # blows the app up. The development machine runs 3.13 so it never showed —
    # exactly the kind of bug that only appears on somebody else's machine.
    def _on(dieu_kien: bool) -> str:
        return " on" if dieu_kien else ""

    chips = "".join(
        f"<button class='stab{_on(tid == dau)}' data-stab='{tid}'>"
        f"{esc(ten)}</button>" for tid, ten, _ in tab)
    panes = "".join(
        f"<div class='stpane{_on(tid == dau)}' data-pane='{tid}'>"
        f"{noi}</div>" for tid, _, noi in tab)

    return (f"<div class=sheethead>Settings</div>"
            f"<div class=stabs>{chips}</div>{panes}")


def _lam_lai(rows: int, files: int, mb: float, backup_dir: str) -> str:
    """The button that returns the app to its original state.

    Two latches, both of them there because something really went wrong once:
      - the word DELETE has to be typed correctly before the button works (the
        server checks again too, never trusting the browser side alone);
      - it says UP FRONT how much will be lost, and where the backup will be.
    """
    co = (f"{rows:,} rows of data · {files} files · ~{mb} MB"
          if rows or files else "currently empty")
    return (
        f"<div class=safe>Wipes the profile, the postings scanned, the CVs "
        f"built, the applications tracked, the mailbox connection and the "
        f"Chrome profile — returning the app to the moment it was installed. "
        f"<b>Will be lost: {esc(co)}.</b><br>"
        f"Before deleting, the app packs everything into a .tar.gz at "
        f"<code>{esc(backup_dir)}</code>. If that pack fails, NOTHING is "
        f"deleted.</div>"
        "<div class=dangerrow>"
        "<input class=search id=resetword placeholder='type DELETE to unlock' "
        "autocomplete=off spellcheck=false>"
        "<button class='mbtn kill' data-post='/api/reset' data-arg=''"
        " data-needword=resetword disabled>Delete everything, start over</button>"
        "</div>")
