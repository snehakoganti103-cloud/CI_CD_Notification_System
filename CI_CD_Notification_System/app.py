import os
import hmac
import sqlite3
from functools import wraps
from datetime import datetime, timezone
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-secret-key-before-deployment")
DATABASE = os.path.join(app.root_path, "database.db")


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS repositories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            full_name TEXT NOT NULL,
            github_url TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, full_name)
        );

        CREATE TABLE IF NOT EXISTS builds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repository_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            branch TEXT,
            commit_sha TEXT,
            commit_message TEXT,
            workflow_name TEXT,
            run_url TEXT,
            duration_seconds INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(repository_id) REFERENCES repositories(id) ON DELETE CASCADE
        );
        """)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_user():
    return {"logged_in": "user_id" in session, "current_user_name": session.get("user_name")}


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or len(password) < 8:
            flash("Enter your name, a valid email, and a password with at least 8 characters.", "error")
            return render_template("register.html")
        try:
            with get_db() as db:
                cur = db.execute(
                    "INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                    (name, email, generate_password_hash(password), datetime.now(timezone.utc).isoformat())
                )
                session["user_id"] = cur.lastrowid
                session["user_name"] = name
            flash("Account created successfully. Add your first repository.", "success")
            return redirect(url_for("repositories"))
        except sqlite3.IntegrityError:
            flash("That email address is already registered.", "error")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        with get_db() as db:
            user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            return redirect(url_for("dashboard"))
        flash("Incorrect email or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    uid = session["user_id"]
    with get_db() as db:
        repos = db.execute("SELECT * FROM repositories WHERE user_id=? ORDER BY created_at DESC", (uid,)).fetchall()
        stats = db.execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN b.status='success' THEN 1 ELSE 0 END) AS passed,
                   SUM(CASE WHEN b.status='failure' THEN 1 ELSE 0 END) AS failed
            FROM builds b JOIN repositories r ON b.repository_id=r.id
            WHERE r.user_id=?
        """, (uid,)).fetchone()
        recent = db.execute("""
            SELECT b.*, r.full_name FROM builds b
            JOIN repositories r ON b.repository_id=r.id
            WHERE r.user_id=? ORDER BY b.id DESC LIMIT 8
        """, (uid,)).fetchall()
    return render_template("dashboard.html", repositories=repos, stats=stats, recent_builds=recent)


@app.route("/repositories", methods=["GET", "POST"])
@login_required
def repositories():
    uid = session["user_id"]
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        github_url = request.form.get("github_url", "").strip()
        if not full_name or "/" not in full_name:
            flash("Enter the repository as owner/repository-name.", "error")
        else:
            name = full_name.split("/", 1)[1]
            try:
                with get_db() as db:
                    db.execute(
                        "INSERT INTO repositories(user_id,name,full_name,github_url,created_at) VALUES(?,?,?,?,?)",
                        (uid, name, full_name, github_url or f"https://github.com/{full_name}",
                         datetime.now(timezone.utc).isoformat())
                    )
                flash("Repository added. Add the GitHub Actions secrets shown below.", "success")
            except sqlite3.IntegrityError:
                flash("This repository is already connected to your account.", "error")
        return redirect(url_for("repositories"))

    with get_db() as db:
        repos = db.execute("SELECT * FROM repositories WHERE user_id=? ORDER BY id DESC", (uid,)).fetchall()
    return render_template("repositories.html", repositories=repos)


@app.route("/repositories/<int:repo_id>/delete", methods=["POST"])
@login_required
def delete_repository(repo_id):
    with get_db() as db:
        db.execute("DELETE FROM repositories WHERE id=? AND user_id=?", (repo_id, session["user_id"]))
    flash("Repository removed.", "success")
    return redirect(url_for("repositories"))


@app.route("/build-history")
@login_required
def build_history():
    with get_db() as db:
        builds = db.execute("""
            SELECT b.*, r.full_name FROM builds b
            JOIN repositories r ON b.repository_id=r.id
            WHERE r.user_id=? ORDER BY b.id DESC
        """, (session["user_id"],)).fetchall()
    return render_template("build_history.html", builds=builds)


@app.route("/build/<int:build_id>")
@login_required
def failure_details(build_id):
    with get_db() as db:
        build = db.execute("""
            SELECT b.*, r.full_name FROM builds b
            JOIN repositories r ON b.repository_id=r.id
            WHERE b.id=? AND r.user_id=?
        """, (build_id, session["user_id"])).fetchone()
    if not build:
        abort(404)
    return render_template("failure_details.html", build=build)


@app.route("/api/builds", methods=["POST"])
def receive_build():
    """GitHub Actions webhook endpoint. Protect it with a long random shared token."""
    expected = os.environ.get("CI_NOTIFICATION_TOKEN", "")
    supplied = request.headers.get("X-CI-TOKEN", "")
    if not expected or not hmac.compare_digest(expected, supplied):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    full_name = (data.get("repository") or "").strip()
    status = (data.get("status") or "").lower()
    if not full_name or status not in {"success", "failure", "cancelled"}:
        return jsonify({"error": "repository and valid status are required"}), 400

    with get_db() as db:
        repo = db.execute("SELECT id FROM repositories WHERE full_name=?", (full_name,)).fetchone()
        if not repo:
            return jsonify({"error": f"Repository {full_name} is not registered"}), 404
        cur = db.execute("""
            INSERT INTO builds(repository_id,status,branch,commit_sha,commit_message,
                               workflow_name,run_url,duration_seconds,created_at)
            VALUES(?,?,?,?,?,?,?,?,?)
        """, (
            repo["id"], status, data.get("branch", ""), data.get("commit_sha", ""),
            data.get("commit_message", ""), data.get("workflow_name", ""),
            data.get("run_url", ""), int(data.get("duration_seconds") or 0),
            datetime.now(timezone.utc).isoformat()
        ))
        build_id = cur.lastrowid

    return jsonify({"message": "Build notification stored", "build_id": build_id}), 201


@app.errorhandler(404)
def not_found(_error):
    return render_template("index.html"), 404


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
