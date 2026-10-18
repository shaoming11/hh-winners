"""Build the hosted AutoChem dashboard (Vercel) from benchsim's dashboard page.

    python tools/build_public_web.py assets                                  # -> web_public/app.js, style.css (commit + push them)
    python tools/build_public_web.py page <tunnel URL> <commit sha>          # -> out/autochem_web/index.html (deploy that)

The page is benchsim/dashboard/web unchanged except that its live feed, camera and view verbs go to the given
backend URL (the read-only tools/public_proxy.py behind a tunnel) instead of the page's own origin, and the
title says AutoChem. The hosted page is one index.html: the backend URL inline, app.js and style.css from the public
repo through jsDelivr (pinned to a commit). Rebuild the page and redeploy when the tunnel URL changes.
"""
import json
import pathlib
import sys

SOFTWARE = pathlib.Path(__file__).resolve().parents[1]
WEB = SOFTWARE / "benchsim" / "benchsim" / "dashboard" / "web"
OUT = SOFTWARE / "out" / "autochem_web"
ASSETS = SOFTWARE / "web_public"
CDN = "https://cdn.jsdelivr.net/gh/shaoming11/hh-winners@%s/software/web_public/%s"


def assets():
    ASSETS.mkdir(exist_ok=True)
    js = (WEB / "app.js").read_text()
    for old, new in (("new EventSource('/events')", "new EventSource(API + '/events')"),
                     ("fetch('/api/' + cmd", "fetch(API + '/api/' + cmd"),
                     ("fetch('/api/view'", "fetch(API + '/api/view'"),
                     ("img.src = '/stream.mjpg?t='", "img.src = API + '/stream.mjpg?t='")):
        assert old in js, old
        js = js.replace(old, new)
    (ASSETS / "app.js").write_text("const API = window.AUTOCHEM_API || '';\n" + js)
    (ASSETS / "style.css").write_text((WEB / "style.css").read_text())
    print("assets in", ASSETS)


def page(api, sha):
    OUT.mkdir(parents=True, exist_ok=True)
    html = (WEB / "index.html").read_text().replace("<title>Wet Lab Bench · live</title>", "<title>AutoChem · live bench</title>")
    html = html.replace('<link rel="stylesheet" href="/style.css">', '<link rel="stylesheet" href="%s">' % (CDN % (sha, "style.css")))
    html = html.replace('<script src="/app.js"></script>',
                        '<script>window.AUTOCHEM_API = %s;</script>\n<script src="%s"></script>' % (json.dumps(api.rstrip("/")), CDN % (sha, "app.js")))
    assert CDN % (sha, "app.js") in html and CDN % (sha, "style.css") in html
    (OUT / "index.html").write_text(html)
    print("page", OUT / "index.html", "->", api)


def main():
    if sys.argv[1] == "assets": assets()
    else: page(sys.argv[2], sys.argv[3])


if __name__ == "__main__":
    main()
