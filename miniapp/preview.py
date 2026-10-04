"""Local UI preview with bundled artwork; no bot or API actions are started."""

import argparse

from aiohttp import web

from miniapp.server import ARTWORK, ARTWORK_NAMES, STATIC


async def preview_file(request):
    if request.path.startswith("/assets/"):
        name = request.match_info["name"]
        if name not in ARTWORK_NAMES:
            raise web.HTTPNotFound()
        return web.FileResponse(ARTWORK / name)
    paths = {"/": "index.html", "/app.js": "app.js", "/styles.css": "styles.css"}
    return web.FileResponse(STATIC / paths[request.path])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8088)
    args = parser.parse_args()
    app = web.Application()
    app.add_routes([web.get(path, preview_file) for path in ["/", "/app.js", "/styles.css", "/assets/{name}"]])
    web.run_app(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
