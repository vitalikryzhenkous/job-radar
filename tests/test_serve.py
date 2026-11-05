"""jr serve: правка навыков, статусы, защита API (токен, Host, Origin, только justjoin)."""
import http.client
import json
import shutil
import threading
from http.server import ThreadingHTTPServer

import pytest
import yaml

from helpers import FIX
from jobradar import poolmap, serve, skills


def test_set_level_keeps_comments(tmp_path):
    p = tmp_path / "profile.yaml"
    shutil.copy(FIX / "profile.yaml", p)
    p.write_text(p.read_text(encoding="utf-8").replace("{name: React, level: strong}",
                                                       "{name: React, level: strong}   # мой комментарий"), encoding="utf-8")
    assert skills.set_level("react", "basic", p, tmp_path / "logs") == "changed"
    assert skills.set_level("React", "basic", p, tmp_path / "logs") == "same"
    assert skills.set_level("GCP", "pet", p, tmp_path / "logs") == "added"
    text = p.read_text(encoding="utf-8")
    assert "{name: React, level: basic}   # мой комментарий" in text
    got = {s["name"]: s["level"] for s in yaml.safe_load(text)["skills"]}
    assert got["React"] == "basic" and got["GCP"] == "pet" and got["TypeScript"] == "strong"
    assert len(list((tmp_path / "logs").glob("profile.yaml.bak-*"))) >= 1
    for bad in [("React", "guru"), ("x: y", "basic")]:
        with pytest.raises(ValueError):
            skills.set_level(*bad, p, tmp_path / "logs")


def test_status_roundtrip(tmp_path):
    poolmap.set_status("acme-dev", "applied", "через сайт", tmp_path)
    assert poolmap.statuses(tmp_path)["acme-dev"]["status"] == "applied"
    poolmap.set_status("acme-dev", "", pool_root=tmp_path)
    assert poolmap.statuses(tmp_path) == {}
    with pytest.raises(ValueError):
        poolmap.set_status("acme-dev", "hired", pool_root=tmp_path)


@pytest.fixture
def server(tmp_path):
    (tmp_path / "2026-11-05").mkdir()
    job = serve.Job()
    job.start = lambda url: setattr(job, "started", url)          # без сети
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.make_handler("T0K", 0, job, tmp_path))
    port = httpd.server_address[1]
    httpd.RequestHandlerClass = serve.make_handler("T0K", port, job, tmp_path)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield port, job, tmp_path
    httpd.shutdown()


def post(port, path, body, token="T0K", host=None, origin=None):
    """http.client к 127.0.0.1 (urlopen в тестах заблокирован conftest'ом)."""
    h = {"Content-Type": "application/json", "X-JR-Token": token, "Host": host or f"127.0.0.1:{port}"}
    if origin:
        h["Origin"] = origin
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request("POST", path, json.dumps(body), h)
    r = c.getresponse()
    out = r.status, json.loads(r.read())
    c.close()
    return out


def test_api_guards(server):
    port, job, root = server
    ok = {"slug": "acme-dev", "status": "applied"}
    assert post(port, "/api/status", ok, token="wrong")[0] == 403
    assert post(port, "/api/status", ok, host="evil.example")[0] == 403
    assert post(port, "/api/status", ok, origin="https://evil.example")[0] == 403
    assert post(port, "/api/status", ok, origin=f"http://localhost:{port}") == (200, {"ok": "acme-dev"})
    assert poolmap.statuses(root)["acme-dev"]["status"] == "applied"
    code, j = post(port, "/api/scan", {"url": "https://www.linkedin.com/jobs/view/1"})
    assert code == 400 and "justjoin" in j["error"] and not hasattr(job, "started")
    assert post(port, "/api/scan", {"url": "https://justjoin.it/job-offers/all-locations/ai"})[0] == 200
    assert job.started.startswith("https://justjoin.it/")
    for bad in ("../etc", "..", "2026-11-05/../.."):
        assert post(port, "/api/move", {"slug": "x", "decision": "apply", "pool": bad})[0] == 400


def test_seen_registry(tmp_path):
    a, b = tmp_path / "2026-11-01", tmp_path / "2026-11-05"
    a.mkdir(), b.mkdir()
    old = [{"slug": "acme-dev", "company": "Acme", "role": "AI Dev", "url": "u1", "decision": "skip", "status": None},
           {"slug": "beta-dev", "company": "Beta", "role": "Dev", "url": "u2", "decision": "apply", "status": {"status": "rejected"}}]
    poolmap.remember(a, old)
    new = [{"slug": "acme-dev-2", "company": "ACME", "role": "AI  Dev", "url": "u3", "decision": "apply", "status": None},
           {"slug": "gamma-dev", "company": "Gamma", "role": "Dev", "url": "u4", "decision": "apply", "status": None},
           {"slug": "beta-dev", "company": "Beta", "role": "Dev", "url": "u2", "decision": "apply", "status": None}]
    reg = poolmap.remember(b, new)
    keys = {poolmap._key(v["company"], v["role"]): v for v in reg.values()}
    got = {r["slug"]: poolmap._prev(r, reg, keys, b.name) for r in new}
    assert got["acme-dev-2"]["old_no"] and got["acme-dev-2"]["first"] == "2026-11-01"     # перевыложена: по компании+роли
    assert got["beta-dev"]["old_no"] and got["gamma-dev"] is None
    after = poolmap.seen_registry(tmp_path)
    assert after["beta-dev"]["first"] == "2026-11-01" and after["beta-dev"]["last"] == "2026-11-05"
    assert poolmap.remember(b, new) == after                                                 # повтор — без изменений


def test_extension_id_matches_manifest():
    import base64, hashlib
    from helpers import FIX
    key = json.loads((FIX.parent.parent / "extension" / "manifest.json").read_text(encoding="utf-8"))["key"]
    h = hashlib.sha256(base64.b64decode(key)).hexdigest()[:32]
    assert "".join(chr(ord("a") + int(c, 16)) for c in h) == serve.EXT_ID


def test_collect_only_from_extension(server):
    port, job, root = server
    job._go = lambda fn: setattr(job, "went", True)                     # без сети и потоков
    ext = f"chrome-extension://{serve.EXT_ID}"
    good = {"urls": ["https://nofluffjobs.com/pl/job/frontend-developer-acme-remote"]}
    assert post(port, "/api/collect", good, token="", origin=f"http://127.0.0.1:{port}")[0] == 403   # даже своя страница
    assert post(port, "/api/collect", good, token="", origin="chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")[0] == 403
    assert post(port, "/api/collect", good, token="")[0] == 403                                       # без Origin
    code, j = post(port, "/api/collect", {"urls": ["https://www.linkedin.com/jobs/view/1"]}, token="", origin=ext)
    assert code == 400 and not hasattr(job, "went")
    assert post(port, "/api/collect", good, token="", origin=ext) == (200, {"ok": "started", "n": 1})
    assert job.went
