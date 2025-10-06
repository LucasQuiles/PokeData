"""Flask web app for running the Pokémon card OCR pipeline locally."""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path
from typing import Iterable

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

from datetime import datetime

from pokedata_core.logging_utils import get_logger, setup_logging
from pokedata_core.pipeline import ensure_dependencies_ready, process_to_csv
from pokedata_core.review_store import (
    append_feedback,
    get_image_path,
    list_runs,
    load_run,
    low_confidence_entries,
    read_annotations,
    store_run,
    write_annotations,
)


logger = get_logger("web")


ALLOWED_EXTENSIONS: Iterable[str] = {"pdf", "png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp"}


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def create_app() -> Flask:
    setup_logging()
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="dev",  # For flashing messages only; replace if deploying
        MAX_CONTENT_LENGTH=200 * 1024 * 1024,  # 200 MB uploads
    )

    ensure_dependencies_ready()

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.post("/process")
    def process_upload():
        upload = request.files.get("card_file")
        dpi = request.form.get("dpi", type=int) or 300
        limit = request.form.get("limit", type=int) or 0

        logger.info(
            "Web upload received: filename=%s, content_length=%s, dpi=%s, limit=%s",
            getattr(upload, "filename", None),
            request.content_length,
            dpi,
            limit,
        )

        if upload is None or upload.filename == "":
            flash("Select a PDF or image to process.")
            return redirect(url_for("index"))

        if not _allowed_file(upload.filename):
            flash("Unsupported file type. Upload a PDF or image scan.")
            return redirect(url_for("index"))

        safe_name = secure_filename(upload.filename)

        try:
            with tempfile.TemporaryDirectory(prefix="pokedata_") as tmpdir:
                tmp_path = Path(tmpdir)
                input_path = tmp_path / safe_name
                upload.save(input_path)

                output_csv = tmp_path / f"{input_path.stem}_cards.csv"
                result = process_to_csv(input_path, output_csv, limit=limit, dpi=dpi)
                run_meta = store_run(result, safe_name)

                csv_bytes = (
                    result.csv_path.read_bytes() if result.csv_path and result.csv_path.exists() else b""
                )
                csv_stream = io.BytesIO(csv_bytes)
                csv_stream.seek(0)

            download_name = (
                result.csv_path.name if result.csv_path else f"{input_path.stem}_cards.csv"
            )
            logger.info(
                "Web processing complete: %s -> %s (%d rows)",
                safe_name,
                download_name,
                len(result.rows),
            )
            response = send_file(
                csv_stream,
                mimetype="text/csv",
                as_attachment=True,
                download_name=download_name,
            )
            response.headers["X-Processed-Rows"] = str(len(result.rows))
            response.headers["X-Run-Id"] = run_meta.get("run_id", "")
            return response
        except Exception as exc:  # noqa: BLE001 - surfaced to user via flash
            logger.exception("Web processing failed for %s", safe_name)
            message = str(exc)
            if "Poppler" in message:
                message += " — install with `brew install poppler` and restart the launcher."
            flash(f"Processing failed: {message}")
            return redirect(url_for("index"))

    @app.get("/review")
    def review_index():
        return render_template("review.html")

    @app.get("/api/runs")
    def api_runs():
        runs = list_runs()
        return jsonify(runs)

    @app.get("/api/runs/<run_id>")
    def api_run_details(run_id: str):
        try:
            run = load_run(run_id)
        except FileNotFoundError:
            abort(404)
        run_meta = dict(run)
        run_meta.pop("run_dir", None)
        return jsonify(run_meta)

    @app.get("/review/<run_id>/images/<path:image_name>")
    def review_image(run_id: str, image_name: str):
        try:
            image_path = get_image_path(run_id, image_name)
        except FileNotFoundError:
            abort(404)
        return send_from_directory(image_path.parent, image_path.name)

    @app.get("/api/runs/<run_id>/annotations/<path:image_name>")
    def api_get_annotations(run_id: str, image_name: str):
        try:
            annotations = read_annotations(run_id, image_name)
        except FileNotFoundError:
            abort(404)
        return jsonify({"annotations": annotations})

    @app.post("/api/runs/<run_id>/annotations/<path:image_name>")
    def api_save_annotations(run_id: str, image_name: str):
        payload = request.get_json(silent=True) or {}
        annotations = payload.get("annotations", [])
        if not isinstance(annotations, list):
            abort(400)
        try:
            write_annotations(run_id, image_name, annotations)
        except FileNotFoundError:
            abort(404)
        return jsonify({"saved": len(annotations)})

    @app.get("/api/runs/<run_id>/low-confidence")
    def api_low_confidence(run_id: str):
        threshold = request.args.get("threshold", type=float)
        if threshold is None:
            threshold = float(os.getenv("POKEDATA_CONFIDENCE_THRESHOLD", "0.9"))
        try:
            entries = low_confidence_entries(run_id, threshold=threshold)
        except FileNotFoundError:
            abort(404)
        base_url = url_for("review_image", run_id=run_id, image_name="", _external=False)
        base_url = base_url.rstrip("/")
        enriched = []
        for entry in entries:
            image_name = entry.get("image")
            image_url = f"{base_url}/{image_name}" if image_name else None
            enriched.append(
                {
                    **entry,
                    "image_url": image_url,
                }
            )
        return jsonify({"items": enriched, "threshold": threshold})

    @app.post("/api/runs/<run_id>/feedback")
    def api_feedback(run_id: str):
        payload = request.get_json(silent=True) or {}
        required = {"page_index", "image", "field", "action"}
        if not required.issubset(payload):
            abort(400)
        action = payload.get("action")
        if action not in {"save", "skip"}:
            abort(400)
        if action == "save" and not payload.get("value"):
            abort(400)
        payload["timestamp"] = datetime.utcnow().isoformat()
        feedback_path = append_feedback(run_id, payload)
        logger.info("Human feedback recorded at %s", feedback_path)
        return jsonify({"status": "ok"})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
