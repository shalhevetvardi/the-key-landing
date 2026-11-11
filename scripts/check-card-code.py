"""בדיקה של מספר הכרטיס בדף המפתח (12-11-2026): שני הכפתורים לנועם נושאים את מספר הביקור (#v-) ואת הקוד האישי (#w-)
כשהגיעו מקישור אישי (?who=), והדפדפן זוכר את הקוד 30 יום לביקור חוזר. כמו scripts/check-noam-visit-id.py ב-tironot-landing.

מגיש את הריפו מקומית ופותח את הדף בדפדפן שמרנדר (playwright). שום בקשה לא יוצאת מהמחשב: האוסף והשאר חסומים.

    <python עם playwright> scripts/check-card-code.py            # מתיקיית הריפו
    <python עם playwright> scripts/check-card-code.py <תיקייה>  # עותק אחר של הדף

ב-shalhevet2: ~/קוד/sales-automation/venv/bin/python."""
import http.server, json, re, socketserver, sys, threading
from functools import partial
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import sync_playwright

ROOT = sys.argv[1] if len(sys.argv) > 1 else str(__import__("pathlib").Path(__file__).resolve().parent.parent)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = socketserver.TCPServer(("127.0.0.1", 0), partial(Quiet, directory=ROOT)); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{port}"
KEY_TEXT = "לשאלות על המפתח"
HELP_TEXT = "נתקלתי בבעיה בהרשמה למפתח"  # הקישור "נתקעת בהרשמה? אפשר לכתוב לנועם" (12-11-2026): ההודעה המוכנה שנועם מתחיל איתה מסלול אבחון
DAY = 86400000
fails = 0


def fresh(b):
    c = b.new_context(viewport={"width": 390, "height": 844})
    ev = []
    def rt(r):
        u = r.request.url
        if u.startswith(base):
            return r.continue_()
        if "r.aimprove.co.il/e" in u and r.request.post_data:
            ev.append(json.loads(r.request.post_data))
        return r.abort()
    c.route("**/*", rt)
    return c, ev


def visit(pg, path, events, who):
    events.clear()
    pg.goto(f"{base}/{path}", wait_until="domcontentloaded"); pg.wait_for_timeout(800)
    vid = pg.evaluate("sessionStorage.getItem('aim_vid')") or ""
    texts = [parse_qs(urlparse(h).query)["text"][0] for h in
             pg.eval_on_selector_all('a[href*="wa.me/972559397247"]', "els => els.map(e => e.href)")]
    tail = f"#v-{vid}" + (f" #w-{who}" if who else "")
    ok = (len(texts) == 3 and all((t.startswith(KEY_TEXT) or t.startswith(HELP_TEXT)) and t.endswith(tail) for t in texts)
          and len(vid) == 16 and {e.get("who", "") for e in events} == {who} and bool(events) and "who=" not in pg.url)
    return ok, f"buttons={len(texts)} vid_len={len(vid)} events={len(events)} event_who={sorted({e.get('who', '') for e in events})}"


def check(name, ok, info=""):
    global fails
    fails += not ok
    print(("OK  " if ok else "FAIL"), name, info)


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx, ev = fresh(b); pg = ctx.new_page()
    check("link with the card number", *visit(pg, "index.html?who=mc12345&src=test-cardcode", ev, "mc12345"))
    check("return visit in a new tab, within 30 days", *visit(ctx.new_page(), "index.html?src=test-cardcode", ev, "mc12345"))
    pg3 = ctx.new_page()
    ok, info = visit(pg3, "index.html?who=mc777&src=test-cardcode", ev, "mc777")
    kept = pg3.evaluate("JSON.parse(localStorage.getItem('aim_who_kept')||'null')") or {}
    check("a link of another person replaces it", ok and kept.get("w") == "mc777", info)
    pg3.goto(f"{base}/index.html?aim_optout=1", wait_until="domcontentloaded"); pg3.wait_for_timeout(400)
    check("this-is-me device forgets it", pg3.evaluate("localStorage.getItem('aim_who_kept')") is None)
    ctx.close()
    for label, shift in (("older than 30 days", -31 * DAY), ("timestamp in the future", DAY)):
        ctx, ev = fresh(b); pg = ctx.new_page()
        pg.goto(f"{base}/index.html?src=test-cardcode", wait_until="domcontentloaded"); pg.wait_for_timeout(300)
        pg.evaluate(f"localStorage.setItem('aim_who_kept', JSON.stringify({{w: 'mc999', t: Date.now() + ({shift})}}))")
        pg2 = ctx.new_page()
        ok, info = visit(pg2, "index.html?src=test-cardcode", ev, "")
        check(label + ": not used, and removed", ok and pg2.evaluate("localStorage.getItem('aim_who_kept')") is None, info)
        ctx.close()
    ctx, ev = fresh(b)
    check("another browser gets no code", *visit(ctx.new_page(), "index.html?src=test-cardcode", ev, ""))
    ctx.close(); b.close()
srv.shutdown()
sys.exit(1 if fails else 0)
