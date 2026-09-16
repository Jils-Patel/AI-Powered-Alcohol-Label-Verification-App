import csv
import io
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from label_verifier import verify_label

load_dotenv()

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_CONTENT_LENGTH = 15 * 1024 * 1024  # 15 MB per request, generous for a batch

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH


def _save_upload(file_storage):
    ext = os.path.splitext(file_storage.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {file_storage.filename}")
    safe_name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_DIR, safe_name)
    file_storage.save(path)
    return path


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/verify", methods=["POST"])
def api_verify():
    if "image" not in request.files:
        return jsonify({"error": "No image file provided."}), 400

    declared = {
        "brand_name": request.form.get("brand_name", "").strip(),
        "class_type": request.form.get("class_type", "").strip(),
        "alcohol_content": request.form.get("alcohol_content", "").strip(),
        "net_contents": request.form.get("net_contents", "").strip(),
        "producer_info": request.form.get("producer_info", "").strip(),
        "country_of_origin": request.form.get("country_of_origin", "").strip(),
    }

    path = None
    try:
        path = _save_upload(request.files["image"])
        result = verify_label(path, declared)
        result["filename"] = request.files["image"].filename
        return jsonify(result)
    except Exception as exc:  # noqa: BLE001 - surface a clean error to the UI
        return jsonify({"error": str(exc)}), 500
    finally:
        if path and os.path.exists(path):
            os.remove(path)


@app.route("/api/verify-batch", methods=["POST"])
def api_verify_batch():
    images = request.files.getlist("images")
    if not images:
        return jsonify({"error": "No image files provided."}), 400

    declared_by_filename = {}
    csv_file = request.files.get("manifest")
    if csv_file:
        try:
            text = csv_file.stream.read().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                filename = (row.get("filename") or "").strip()
                if filename:
                    declared_by_filename[filename] = {
                        "brand_name": row.get("brand_name", "").strip(),
                        "class_type": row.get("class_type", "").strip(),
                        "alcohol_content": row.get("alcohol_content", "").strip(),
                        "net_contents": row.get("net_contents", "").strip(),
                        "producer_info": row.get("producer_info", "").strip(),
                        "country_of_origin": row.get("country_of_origin", "").strip(),
                    }
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": f"Could not parse manifest CSV: {exc}"}), 400

    # Save uploads up front (cheap, must happen on this thread), then run the
    # slow part -- the vision API calls -- concurrently, since a real seasonal
    # spike could mean dozens of labels and these calls are I/O-bound.
    jobs = []  # (original_index, filename, saved_path or None, error or None)
    for idx, image in enumerate(images):
        try:
            path = _save_upload(image)
            jobs.append((idx, image.filename, path, None))
        except Exception as exc:  # noqa: BLE001
            jobs.append((idx, image.filename, None, str(exc)))

    results = [None] * len(jobs)

    def _run(job):
        idx, filename, path, save_error = job
        if save_error:
            return idx, {"filename": filename, "error": save_error}
        try:
            declared = declared_by_filename.get(filename, {})
            result = verify_label(path, declared)
            result["filename"] = filename
            return idx, result
        except Exception as exc:  # noqa: BLE001
            return idx, {"filename": filename, "error": str(exc)}
        finally:
            if os.path.exists(path):
                os.remove(path)

    with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as pool:
        for idx, result in pool.map(_run, jobs):
            results[idx] = result

    return jsonify({"results": results})


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
