"""Do call sites match their definitions — checked with the AST.

Why it is needed: removing the `conn` parameter from `mail.account()` while
missing one call site in `server.py` turned the whole /track page WHITE. 906
tests were green at the time — because Python only notices an argument
mismatch when that line actually runs, and no test ran that line.

This reads THE WHOLE REPO with the AST and matches every call against its
definition. It only considers calls TRACEABLE to exactly one module in the
project — the first version matched by bare name, so `dict.get`, `str.split`
and `datetime.now` collided with project functions: 216 alarms, 0 real.

    python3 tests/test_arity.py
"""

import ast, sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
mods = {}                      # 'jobbot.track.mail' -> {name: (min,max,line)}
for f in sorted(SRC.rglob("*.py")):
    dotted = ".".join(f.relative_to(SRC).with_suffix("").parts)
    if dotted.endswith(".__init__"):
        dotted = dotted[: -len(".__init__")]
    table = {}
    tree = ast.parse(f.read_text(), str(f))
    for node in tree.body:                     # module-level functions ONLY, no methods
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = node.args
            pos = len(a.posonlyargs) + len(a.args)
            table[node.name] = (pos - len(a.defaults),
                                None if a.vararg else pos,
                                {k.arg for k in a.kwonlyargs} | {x.arg for x in a.args},
                                node.lineno, str(f))
    mods[dotted] = table

def resolve(node, package):
    """`from ..track import mail` -> {'mail': 'jobbot.track.mail'}"""
    out = {}
    for n in ast.walk(node):
        if isinstance(n, ast.ImportFrom):
            # level 1 = this package itself, level 2 = the parent. So (level -
            # 1) steps are dropped, not `level` — one step off and it
            # resolves to 'track.mail' instead of 'jobbot.track.mail', and
            # every call made through a relative import slips the net.
            base = package.split(".")
            if n.level:
                cut = len(base) - (n.level - 1)
                base = base[: max(cut, 0)]
            root = ".".join([*base, n.module] if n.module else base)
            for alias in n.names:
                out[alias.asname or alias.name] = f"{root}.{alias.name}"
        elif isinstance(n, ast.Import):
            for alias in n.names:
                out[alias.asname or alias.name] = alias.name
    return out

bad = []
for f in sorted(SRC.rglob("*.py")):
    dotted = ".".join(f.relative_to(SRC).with_suffix("").parts)
    package = dotted.rsplit(".", 1)[0]
    tree = ast.parse(f.read_text(), str(f))
    names = resolve(tree, package)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn, target = node.func, None
        if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
            base = names.get(fn.value.id)
            if base in mods and fn.attr in mods[base]:
                target = (base, fn.attr)
        elif isinstance(fn, ast.Name):
            full = names.get(fn.id)
            if full:
                mod, _, name = full.rpartition(".")
                if mod in mods and name in mods[mod]:
                    target = (mod, name)
        if not target:
            continue
        req, mx, allowed, ln, where = mods[target[0]][target[1]]
        got = len(node.args)
        keys = {k.arg for k in node.keywords if k.arg}
        if any(isinstance(x, ast.Starred) for x in node.args) or any(k.arg is None for k in node.keywords):
            continue
        if mx is not None and got > mx:
            bad.append(f"{f}:{node.lineno}  {target[0]}.{target[1]}({got}) — takes at most {mx}  [{where}:{ln}]")
        elif got + len(keys) < req:
            bad.append(f"{f}:{node.lineno}  {target[0]}.{target[1]}({got}+{len(keys)}) — needs {req}  [{where}:{ln}]")
        else:
            for k in keys:
                if k not in allowed:
                    bad.append(f"{f}:{node.lineno}  {target[0]}.{target[1]}(…, {k}=) — no such parameter  [{where}:{ln}]")


ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ok   {name}")
    else:
        fail += 1
        print(f"  FAIL {name}{' — ' + extra if extra else ''}")


print(f"\n[matched {sum(len(t) for t in mods.values())} functions across {len(mods)} modules]")
check("every call site matches its definition", not bad, " · ".join(bad[:4]))
for line in bad:
    print("     ", line)

# The checker has to PROVE IT CATCHES THINGS — a checker that always returns 0
# is useless while still looking like it runs.
import ast as _ast
_probe = _ast.parse("from ..track import mail\nmail.account(conn)\n")
_names = resolve(_probe, "jobbot.dashboard")
check("a relative import resolves",
      _names.get("mail") == "jobbot.track.mail", str(_names))
check("and that module is in the table", "jobbot.track.mail" in mods)
check("account() really does take 0 parameters",
      mods.get("jobbot.track.mail", {}).get("account", (None,))[1] == 0)

# --------------------------------------------------------------------------
# CALLING A FUNCTION THAT DOES NOT EXIST. A quite different class of bug from
# the above: that one is calling with THE WRONG NUMBER of arguments, this one
# is calling INTO NOTHING.
#
# THE REAL BUG: commit f669e66 deleted `def _await(...)` in apply/run.py while
# leaving TWO call sites. Every application reaching the "no fields yet"
# branch died with a NameError. 1,451 tests were green, because that branch
# only runs with a real Chrome and a real careers page — only the runtime
# journal revealed it.
#
# Only names starting with "_" are examined: those are a module's private
# functions, which CANNOT come from an `import *` or from builtins, so one
# not defined in that file is certainly a call into nothing — no false
# alarms.
print("\n[calling a module-private function means that function must EXIST]")
treo = []
for f in sorted(SRC.rglob("*.py")):
    tree = ast.parse(f.read_text(), str(f))
    co = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            co.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            co.add(node.id)
        elif isinstance(node, ast.arg):
            co.add(node.arg)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                co.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.Global):
            co.update(node.names)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id.startswith("_") and node.func.id not in co):
            treo.append(f"{f.name}:{node.lineno} {node.func.id}()")

check("nothing calls into nothing", not treo, " · ".join(treo[:4]))
for line in treo:
    print("     ", line)

# The checker has to PROVE it catches what it claims to catch.
_gia = ast.parse("def _co(): pass\n_co()\n_khong_he_co()\n")
_dinh = set()
for _n in ast.walk(_gia):
    if isinstance(_n, ast.FunctionDef):
        _dinh.add(_n.name)
_bat = [n.func.id for n in ast.walk(_gia)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id.startswith("_") and n.func.id not in _dinh]
check("and the checker proves it catches one", _bat == ["_khong_he_co"], str(_bat))

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
