# TTB Label Verification Assistant

A prototype that helps TTB compliance agents check an alcohol label photo
against the corresponding COLA application in seconds instead of minutes,
built for the take-home assessment described in
[treasurytakehome-rgb/instructions](https://github.com/treasurytakehome-rgb/instructions).

## Why this approach

The discovery notes point pretty directly at a vision-LLM pipeline rather
than classic OCR + regex:

- **Sarah Chen** needs ~5 second turnaround (the prior vendor's 30–40s
  pilot failed) and an interface non-technical agents can use unassisted.
- **Dave Morrison** warned against brittle exact-match rejection — "minor
  formatting differences shouldn't trigger automatic rejection." That
  argues for fuzzy comparison with a human-review middle state, not a
  binary pass/fail.
- **Jenny Park** needs the Government Warning checked *precisely*
  (verbatim wording, all-caps + bold "GOVERNMENT WARNING:" lead-in per
  27 CFR 16.21), and wants the tool to tolerate imperfectly photographed
  labels.
- **Marcus Williams** confirmed the prototype doesn't need to integrate
  with the .NET/COLA system or worry about production security, and that
  outbound network calls to a cloud API are the known risk (not a
  blocker for a prototype, but worth flagging for a production version).

A single multimodal LLM call reads the label image, transcribes the six
required fields, *and* visually judges formatting (caps/bold) in one
pass — something plain OCR can't reliably do. That call is the one
external dependency; everything else (fuzzy matching, verdicts, UI) runs
locally, which also minimizes what crosses the FedRAMP network boundary
Marcus mentioned.

## What it does

1. Upload a label photo (single label, or a batch of many).
2. Optionally provide the values declared on the COLA application — by
   hand for a single label, or via a CSV manifest for a batch.
3. The app extracts: brand name, class/type, alcohol content, net
   contents, producer info, country of origin (imports only), and the
   government warning statement — the full field list called out in the
   instructions' "About TTB Label Requirements" section.
4. Each field gets a verdict:
   - **Match** — extracted value agrees with the application.
   - **Needs Review** — close but not exact (e.g. punctuation/spacing
     differences), or the model couldn't confidently read a field off a
     low-quality photo — surfaced to a human rather than auto-rejected
     or auto-failed.
   - **Mismatch** — meaningfully different, or the warning statement
     fails wording/formatting requirements.
   - **Not Checked** — no application value was provided for that field
     (expected for country of origin on most domestic labels).
   - **Partial** (batch/overall only) — checked fields agree, but some
     fields had no application value to compare against.
5. Results, plus per-run processing time, render immediately; batch runs
   show a sortable table with an expandable per-label breakdown and CSV
   export.

## Tech stack

- **Backend:** Python / Flask (`app.py`, `label_verifier.py`)
- **Extraction model:** OpenAI `gpt-4o-mini` (vision), swappable via
  `OPENAI_MODEL` — chosen over `gpt-4o` because it hits sub-5-second
  responses consistently in testing while extracting all fields
  correctly; bump to `gpt-4o` if accuracy matters more than latency for
  a given deployment.
- **Frontend:** plain HTML/CSS/JS (no build step, so it runs anywhere
  Python runs — relevant given the FedRAMP/Azure constraints mentioned).
- **Matching:** `difflib` sequence similarity with three thresholds
  (match / review / mismatch), plus a hardcoded copy of the 27 CFR 16.21
  warning text for strict comparison.

## Local setup

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and set OPENAI_API_KEY=sk-...

python app.py                    # serves on http://localhost:5000
# if port 5000 is taken (e.g. macOS AirPlay), run: PORT=5001 python app.py
```

Open the printed URL, upload a label image, and try it. A batch CSV
manifest format is documented in the "Batch Upload" tab of the UI
(downloadable sample included).

## Deploying

Any host that runs a Python web process works (Render, Railway, Fly.io,
an Azure App Service/Web App, etc.). General shape:

1. Push this repo to GitHub.
2. Create a new web service pointing at the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app` (add `gunicorn` to
   `requirements.txt` for production, or use `python app.py` for a
   quick prototype deploy)
5. Set the `OPENAI_API_KEY` environment variable in the host's dashboard
   — never commit it.

Since Marcus noted the network is firewalled against many outbound
cloud connections, a production rollout would need the OpenAI endpoint
allow-listed (or the extraction call swapped for an in-VPC/Azure-hosted
vision model) — noted here as a known gap for the prototype, not solved
by it.

## Assumptions and trade-offs

- **27 CFR 16.21 is used as the canonical Government Warning text.** The
  instructions describe the requirement (exact wording, all-caps + bold
  lead-in) without pasting the statutory text itself, so the actual
  wording is hardcoded from the real regulation rather than invented.
- **Country of origin is only checked when declared.** It's legally
  required for imports only, so a domestic label with no country of
  origin printed is expected and shown as "Not Checked," not a defect.
- **Fuzzy matching thresholds (97% / 80% / below) are a judgment call**,
  tuned against the "STONE'S THROW" vs. "Stone's Throw" style case Dave
  described — same brand, different casing/punctuation, shouldn't
  auto-reject. A production version would want these thresholds
  validated against a larger set of real labels, ideally with agent
  feedback loop to tune them.
- **Test labels are synthetically generated** (Pillow-rendered, plus one
  matching the instructions' own "OLD TOM DISTILLERY" example) rather
  than photographed, since no real label images were provided.

## Known limitations (prototype scope)

- No auth — matches the "prototype needn't handle production-level
  security" note, but is not appropriate to expose broadly as-is.
- Extraction accuracy depends on the vision model and photo quality;
  the UI surfaces the model's own confidence and image-quality notes so
  an agent knows when to look closer, but it will occasionally
  misread a badly angled or low-res photo — hence "Needs Review" as a
  first-class outcome rather than forcing a binary call.
- Uploaded images are processed in memory/temp storage and deleted
  immediately after each request; nothing is persisted server-side.
