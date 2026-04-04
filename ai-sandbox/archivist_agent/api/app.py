"""Flask API for the standalone Archivist agent — 14 REST endpoints."""

from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from archivist_agent.core.archivist import Archivist
from archivist_agent.core.models import DataSource, FileRecord, RetentionPolicy

app = Flask(
    __name__,
    template_folder="../templates",
    static_folder="../static",
)

agent = Archivist()


# ------------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------------

@app.route("/")
def dashboard():
    return render_template("dashboard.html")


# ------------------------------------------------------------------
# Status
# ------------------------------------------------------------------

@app.route("/api/status")
def api_status():
    return jsonify(agent.status())


# ------------------------------------------------------------------
# Files (CRUD + search)
# ------------------------------------------------------------------

@app.route("/api/files", methods=["GET"])
def list_files():
    return jsonify([f.to_dict() for f in agent.list_files()])


@app.route("/api/files", methods=["POST"])
def create_file():
    data = request.get_json(force=True)
    if not data or "path" not in data or "category" not in data:
        return jsonify({"error": "path and category are required"}), 400
    retention = RetentionPolicy(data.get("retention", "keep_3_years"))
    record = FileRecord(
        path=data["path"],
        category=data["category"],
        tags=data.get("tags", []),
        retention=retention,
        encrypted=data.get("encrypted", False),
    )
    agent.register_file(record)
    return jsonify(record.to_dict()), 201


@app.route("/api/files/<path:filepath>", methods=["GET"])
def get_file(filepath: str):
    record = agent.get_file(filepath)
    if record is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(record.to_dict())


@app.route("/api/files/<path:filepath>", methods=["DELETE"])
def delete_file(filepath: str):
    if agent.delete_file(filepath):
        return jsonify({"deleted": filepath})
    return jsonify({"error": "not found"}), 404


@app.route("/api/files/search", methods=["GET"])
def search_files():
    query = request.args.get("q")
    category = request.args.get("category")
    tags = request.args.getlist("tag")
    results = agent.search_files(query=query, category=category, tags=tags or None)
    return jsonify([f.to_dict() for f in results])


@app.route("/api/files/retention", methods=["GET"])
def files_due():
    return jsonify([f.to_dict() for f in agent.files_due_for_deletion()])


# ------------------------------------------------------------------
# Profile
# ------------------------------------------------------------------

@app.route("/api/profile", methods=["GET"])
def get_profile():
    return jsonify(agent.get_profile())


@app.route("/api/profile", methods=["PUT"])
def update_profile():
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400
    for key, value in data.items():
        agent.set_profile_field(key, value)
    return jsonify(agent.get_profile())


# ------------------------------------------------------------------
# Data sources
# ------------------------------------------------------------------

@app.route("/api/sources", methods=["GET"])
def list_sources():
    return jsonify([s.to_dict() for s in agent.list_sources()])


@app.route("/api/sources", methods=["POST"])
def add_source():
    data = request.get_json(force=True)
    if not data or "name" not in data or "source_type" not in data:
        return jsonify({"error": "name and source_type are required"}), 400
    key = data["name"].lower().replace(" ", "_")
    source = DataSource(
        name=data["name"],
        source_type=data["source_type"],
        data_types=data.get("data_types", []),
        sync_enabled=data.get("sync_enabled", False),
        config=data.get("config", {}),
    )
    agent.add_source(key, source)
    return jsonify(source.to_dict()), 201


@app.route("/api/sources/<name>/sync", methods=["POST"])
def sync_source(name: str):
    result = agent.sync_source(name)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


# ------------------------------------------------------------------
# Privacy
# ------------------------------------------------------------------

@app.route("/api/privacy/tools", methods=["GET"])
def list_privacy_tools():
    return jsonify([t.to_dict() for t in agent.list_privacy_tools()])


@app.route("/api/privacy/audit", methods=["GET"])
def privacy_audit():
    return jsonify(agent.privacy_audit())


# ------------------------------------------------------------------
# Audit log
# ------------------------------------------------------------------

@app.route("/api/audit", methods=["GET"])
def audit_log():
    limit = request.args.get("limit", 50, type=int)
    return jsonify(agent.get_audit_log(limit=limit))
