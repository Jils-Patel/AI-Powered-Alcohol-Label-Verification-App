"""
Core verification logic for the TTB Alcohol Label Verification prototype.

Pipeline:
  1. Send the label photo to Claude (vision) and get back a structured
     extraction of the six fields TTB agents check by hand.
  2. Compare each extracted field against the value declared on the
     COLA application, using fuzzy matching rather than exact string
     equality -- per Dave Morrison's note that minor formatting
     differences shouldn't cause an automatic rejection.
  3. The Government Warning statement is checked separately and more
     strictly, since Jenny Park flagged that its wording and formatting
     (all-caps "GOVERNMENT WARNING:", verbatim text) are non-negotiable
     under 27 CFR 16.21.
"""
import base64
import difflib
import json
import mimetypes
import os
import re
import time

from openai import OpenAI

MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# The verbatim statement required by 27 CFR 16.21. Numbering ("(1)"/"(2)")
# is normalized away before comparison since it's a formatting detail,
# not a wording difference.
REQUIRED_GOVERNMENT_WARNING = (
    "GOVERNMENT WARNING: ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD NOT "
    "DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF BIRTH "
    "DEFECTS. CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY TO "
    "DRIVE A CAR OR OPERATE MACHINERY, AND MAY CAUSE HEALTH PROBLEMS."
)

FIELD_LABELS = {
    "brand_name": "Brand Name",
    "class_type": "Class/Type Designation",
    "alcohol_content": "Alcohol Content (ABV)",
    "net_contents": "Net Contents",
    "producer_info": "Producer Information",
    "government_warning": "Government Warning Statement",
}

EXTRACTION_PROMPT = """You are assisting a TTB (Alcohol and Tobacco Tax and Trade Bureau) \
compliance agent in reading an alcohol beverage label photograph.

Carefully read the label image and extract exactly these fields. If the photo is \
angled, glare-affected, or partially cut off, do your best and lower your confidence \
score rather than guessing wildly.

Return ONLY a single JSON object (no markdown fences, no commentary) with this shape:

{
  "brand_name": "<string or null>",
  "class_type": "<string or null, e.g. 'Bourbon Whiskey', 'India Pale Ale'>",
  "alcohol_content": "<string or null, e.g. '13.5% ALC/VOL'>",
  "net_contents": "<string or null, e.g. '750 ML'>",
  "producer_info": "<string or null, the bottler/producer name and address as printed>",
  "government_warning": "<string or null, the FULL warning statement text, transcribed verbatim including punctuation. You MUST start the string with the lead-in phrase exactly as printed (e.g. 'GOVERNMENT WARNING:') -- do not omit it or start mid-sentence>",
  "government_warning_all_caps": <true/false, whether 'GOVERNMENT WARNING:' is printed in all capital letters>,
  "government_warning_bold": <true/false, whether the words 'GOVERNMENT WARNING:' appear bold/heavier weight than surrounding text>,
  "image_quality_notes": "<short string: e.g. 'clear', 'slight glare on right edge', 'blurry, low confidence'>",
  "confidence": <number 0-1, your overall confidence in this extraction>
}

Transcribe text exactly as printed (preserve capitalization). Use null for any field \
that is not visible or not present on the label."""


def _encode_image(path):
    mime, _ = mimetypes.guess_type(path)
    if mime is None:
        mime = "image/jpeg"
    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return mime, data


def _get_client():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to your environment or .env file."
        )
    return OpenAI(api_key=api_key)


def extract_label_fields(image_path):
    """Calls a vision-capable LLM on the given image and returns a parsed dict."""
    mime, b64data = _encode_image(image_path)
    client = _get_client()

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=1024,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": EXTRACTION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64data}"},
                    },
                ],
            }
        ],
    )

    raw_text = (response.choices[0].message.content or "").strip()

    # Strip accidental markdown fences just in case.
    raw_text = re.sub(r"^```(?:json)?", "", raw_text.strip())
    raw_text = re.sub(r"```$", "", raw_text.strip()).strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"Could not parse model response as JSON:\n{raw_text}")


def _normalize(text):
    if text is None:
        return ""
    text = text.upper()
    text = re.sub(r"[\(\)\d]", "", text)  # drop numbering like (1) (2)
    text = re.sub(r"[^A-Z%\.\,\s/]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _similarity(a, b):
    return difflib.SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def _verdict_for_similarity(ratio):
    if ratio >= 0.97:
        return "match"
    if ratio >= 0.80:
        return "review"  # close, but not exact -- flag for a human, don't auto-reject
    return "mismatch"


def compare_fields(extracted, declared):
    """
    extracted: dict from extract_label_fields()
    declared:  dict of the values on the COLA application, same keys
               (any of brand_name, class_type, alcohol_content, net_contents,
               producer_info -- government_warning is checked separately)
    """
    results = {}
    for field in ("brand_name", "class_type", "alcohol_content", "net_contents", "producer_info"):
        expected = declared.get(field)
        found = extracted.get(field)
        if not expected:
            results[field] = {
                "label": FIELD_LABELS[field],
                "extracted": found,
                "expected": expected,
                "similarity": None,
                "verdict": "no_data",
            }
            continue
        ratio = _similarity(found or "", expected)
        results[field] = {
            "label": FIELD_LABELS[field],
            "extracted": found,
            "expected": expected,
            "similarity": round(ratio, 3),
            "verdict": _verdict_for_similarity(ratio),
        }

    results["government_warning"] = check_government_warning(extracted)
    return results


def check_government_warning(extracted):
    text = extracted.get("government_warning")
    label = FIELD_LABELS["government_warning"]

    if not text:
        return {
            "label": label,
            "extracted": None,
            "expected": REQUIRED_GOVERNMENT_WARNING,
            "similarity": 0.0,
            "verdict": "mismatch",
            "issues": ["No government warning statement detected on the label."],
        }

    issues = []
    ratio = _similarity(text, REQUIRED_GOVERNMENT_WARNING)

    if not text.strip().upper().startswith("GOVERNMENT WARNING"):
        issues.append("Statement does not begin with the required 'GOVERNMENT WARNING:' lead-in.")

    if ratio < 0.97:
        issues.append("Wording deviates from the statutory text (27 CFR 16.21).")

    if extracted.get("government_warning_all_caps") is False:
        issues.append("'GOVERNMENT WARNING:' is not printed in all capital letters.")

    if extracted.get("government_warning_bold") is False:
        issues.append("'GOVERNMENT WARNING:' does not appear bold.")

    if issues:
        verdict = "mismatch" if ratio < 0.80 else "review"
    else:
        verdict = "match"

    return {
        "label": label,
        "extracted": text,
        "expected": REQUIRED_GOVERNMENT_WARNING,
        "similarity": round(ratio, 3),
        "verdict": verdict,
        "issues": issues,
    }


def verify_label(image_path, declared):
    """End-to-end: extract + compare, with timing."""
    start = time.perf_counter()
    extracted = extract_label_fields(image_path)
    field_results = compare_fields(extracted, declared)
    elapsed = round(time.perf_counter() - start, 2)

    verdicts = [r["verdict"] for r in field_results.values()]
    if "mismatch" in verdicts:
        overall = "mismatch"
    elif "review" in verdicts:
        overall = "review"
    elif verdicts.count("no_data") == len(verdicts):
        overall = "no_data"
    elif "no_data" in verdicts:
        overall = "partial"  # some fields matched, others had no application data to check
    else:
        overall = "match"

    return {
        "extracted": extracted,
        "fields": field_results,
        "overall": overall,
        "processing_seconds": elapsed,
        "image_quality_notes": extracted.get("image_quality_notes"),
        "model_confidence": extracted.get("confidence"),
    }
