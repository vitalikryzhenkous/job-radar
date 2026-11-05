"""jr serve: карта с рабочими кнопками (навыки, скан, move, статусы). Только 127.0.0.1, токен на запуск.

Защита от чужих страниц в том же браузере: POST только с заголовком X-JR-Token (токен есть лишь в нашей
странице), Host — localhost/127.0.0.1 (DNS rebinding), Origin — свой. Скан — только https://justjoin.it/.
Расширение (extension/) токена не знает: /api/collect пускает только Origin chrome-extension://EXT_ID.
Origin ставит сам браузер, чужая страница подделать его не может; ID закреплён ключом "key" в manifest.json.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import fx, poolmap, scan, skills
from .config import load_profile
from .tracker import INDEX

PORT = 8766
EXT_ID = "blkfpbeaffooeaomfglgkeookoadflid"      # = sha256(manifest.key)[:32] в алфавите a-p; тест сверяет


class Job:
    """Один фоновый скан за раз; лог читает страница."""
    def __init__(self):
        self.lock, self.running, self.log, self.error, self.pool = threading.Lock(), False, [], None, None

    def start(self, url: str) -> None:
        self._go(lambda: scan.scan(url, fx.get_rates(), index_path=INDEX, log=self.log.append).parent.name)

    def collect(self, urls: list[str]) -> None:
        for u in urls[:scan.MAX_COLLECT + 1]:      # проверка до старта: ошибка уходит ответом, а не в лог
            scan.site_of(u)

        def run():
            self.summary = scan.collect(urls, fx.get_rates(), index_path=INDEX, log=self.log.append)
            return scan.POOL.joinpath(dt.date.today().isoformat()).name
        self._go(run)

    def _go(self, fn) -> None:
        with self.lock:
            if self.running:
                raise ValueError("скан уже идёт")
            self.running, self.log, self.error, self.pool, self.summary = True, [], None, None, None
        threading.Thread(target=self._run, args=(fn,), daemon=True).start()

    def _run(self, fn) -> None:
        try:
            self.pool = fn()
            self.log.append(f"Готово: {self.pool}")
        except Exception as e:                     # в лог страницы, сервер живёт дальше
            self.error = f"{type(e).__name__}: {e}"
        finally:
            self.running = False

    def state(self) -> dict:
        return {"running": self.running, "log": self.log[-200:], "error": self.error, "pool": self.pool,
                "summary": getattr(self, "summary", None)}


def make_handler(token: str, port: int, job: Job, pool_root: Path = scan.POOL, ext_id: str = EXT_ID):
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {f"http://{h}" for h in hosts}
    ext = f"chrome-extension://{ext_id}"

    def pool_of(name: str | None) -> Path:
        if name:
            p = pool_root / name
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", name) or not p.is_dir():      # только дата: без ../
                raise ValueError(f"нет пула {name}")
            return p
        return poolmap.latest()

    def rescore(pool: Path, profile: dict) -> int:
        return poolmap.rescore(pool, fx.get_rates(), profile, INDEX)

    class H(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):       # тише: только ошибки
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def _host_ok(self) -> bool:
            return self.headers.get("Host") in hosts

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, b"bad host", "text/plain")
            u = urlparse(self.path)
            try:
                if u.path == "/":
                    d = poolmap.data(pool_of(parse_qs(u.query).get("pool", [None])[0]))
                    d["api"] = {"token": token}
                    return self._send(200, poolmap.html(d).encode(), "text/html; charset=utf-8")
                if u.path == "/api/job":
                    return self._json(200, job.state())
                if u.path == "/api/sites":             # шаблоны ссылок для расширения: один источник правды — scan.SITES
                    return self._json(200, {h: rx for h, (_, rx) in scan.SITES.items()})
            except (ValueError, OSError) as e:
                return self._json(400, {"error": str(e)})
            self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if urlparse(self.path).path == "/api/collect":         # только наше расширение
                if not self._host_ok() or self.headers.get("Origin") != ext:
                    return self._json(403, {"error": "forbidden"})
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    if n > 100_000:
                        raise ValueError("слишком большой запрос")
                    urls = json.loads(self.rfile.read(n) or b"{}").get("urls")
                    if not isinstance(urls, list) or not all(isinstance(u, str) for u in urls):
                        raise ValueError("urls: список строк")
                    job.collect(urls)
                    return self._json(200, {"ok": "started", "n": len(urls)})
                except (ValueError, json.JSONDecodeError, AttributeError) as e:
                    return self._json(400, {"error": str(e)})
            if not self._host_ok() or self.headers.get("Origin", next(iter(origins))) not in origins \
                    or not secrets.compare_digest(self.headers.get("X-JR-Token", ""), token):
                return self._json(403, {"error": "forbidden"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if n > 20_000:
                    raise ValueError("слишком большой запрос")
                b = json.loads(self.rfile.read(n) or b"{}")
                path = urlparse(self.path).path
                if path == "/api/move":
                    slug = poolmap.move(pool_of(b.get("pool")), b["slug"], b["decision"], b.get("why", ""))
                    return self._json(200, {"ok": slug})
                if path == "/api/status":
                    poolmap.set_status(b["slug"], b.get("status", ""), b.get("note", ""), pool_root)
                    return self._json(200, {"ok": b["slug"]})
                if path == "/api/skill":
                    what = skills.set_level(b["name"], b["level"])
                    n = rescore(pool_of(b.get("pool")), load_profile()) if what != "same" else 0
                    return self._json(200, {"ok": what, "rescored": n})
                if path == "/api/rescore":
                    return self._json(200, {"rescored": rescore(pool_of(b.get("pool")), load_profile())})
                if path == "/api/scan":
                    url = str(b.get("url", "")).strip()
                    if not url.startswith("https://justjoin.it/"):
                        raise ValueError("только ссылки https://justjoin.it/ (LinkedIn — через jr add)")
                    job.start(url)
                    return self._json(200, {"ok": "started"})
                self._json(404, {"error": "not found"})
            except (KeyError, ValueError, OSError, json.JSONDecodeError) as e:
                self._json(400, {"error": str(e)})

    return H


def serve(port: int = PORT, opener=None) -> None:
    token = secrets.token_urlsafe(24)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(token, port, Job()))
    url = f"http://127.0.0.1:{port}/"          # не localhost: Windows (WSL mirrored) пробует ::1 и ждёт
    print(f"Карта: {url}  (только этот компьютер; Ctrl+C — остановить)")
    if opener:
        opener(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено")
    finally:
        httpd.server_close()
