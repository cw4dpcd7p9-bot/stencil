# stencil

Fill a brief. Stamp out ads.

One Python file, stdlib only, campaigns as JSON on disk.

```bash
python3 server.py
```

Then open [http://127.0.0.1:8788](http://127.0.0.1:8788).

Product, offer, audience, one proof point. Stencil writes five angles of copy for Meta, Google, TikTok, X, and YouTube, then paints a mock at the size you pick. Export the PNG. Save the pack. Nothing leaves the machine.

## Why this instead of an ad SaaS

Those tools want a card and an API key before they show you a headline. This one runs on localhost. The copy engine is templates plus your brief, so you can read every line and change the wording in `public/index.html`. The picture is a canvas, not a model.

Use it to draft. Then tighten by hand. Ads that ship untouched from a generator usually look like ads that shipped untouched from a generator.

## Use it

```bash
python3 server.py
```

Save a campaign from the UI, or post one:

```bash
curl -s -X POST http://127.0.0.1:8788/api/campaigns \
  -H 'content-type: application/json' \
  -d '{"name":"hound-launch","brief":{"product":"HOUND","offer":"spot meme coins before the timeline does"}}'
```

```bash
curl -s http://127.0.0.1:8788/api/campaigns
```

## Config

| env | default | what |
| --- | --- | --- |
| `STENCIL_HOST` | `127.0.0.1` | bind address |
| `STENCIL_PORT` | `8788` | port |

Bind to the LAN:

```bash
STENCIL_HOST=0.0.0.0 python3 server.py
```

## Files

```
server.py           the whole server
public/index.html   the studio
campaigns.json      created on first save
```

No packages. No Docker. No account.
