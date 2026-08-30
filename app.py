from __future__ import annotations

import os
import sqlite3
from datetime import date
from functools import wraps
from pathlib import Path
from uuid import uuid4

from flask import Flask, flash, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("TRX_DATA_DIR", BASE_DIR))
DB_PATH = DATA_DIR / "training.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"
PHOTO_UPLOAD_DIR = (
    DATA_DIR / "uploads" / "photos"
    if "TRX_DATA_DIR" in os.environ
    else BASE_DIR / "static" / "uploads" / "photos"
)
VIDEO_UPLOAD_DIR = DATA_DIR / "video_esplicativi"

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
ALLOWED_VIDEO_EXTENSIONS = {"mp4", "webm", "mov", "m4v"}

ROUTINE = {
    "Lunedi": [
        "TRX Low Row",
        "TRX High Row",
        "TRX Biceps Curl",
        "TRX Standing Fallout",
    ],
    "Martedi": [
        "TRX Chest Press",
        "TRX Triceps Extension",
        "TRX Chest Fly",
        "TRX Standing Plank",
    ],
    "Mercoledi": [
        "Recupero attivo (camminata/cyclette)",
    ],
    "Giovedi": [
        "TRX Assisted Squat",
        "Step-up su sedia",
        "TRX Single-Leg Hinge",
        "TRX Assisted Calf Raise",
    ],
    "Venerdi": [
        "TRX Y-Fly",
        "TRX T-Fly",
        "Super-serie Braccia TRX",
        "TRX Standing Woodchopper",
    ],
    "Sabato": [
        "Attivita libera / recupero",
    ],
    "Domenica": [
        "Attivita libera / recupero",
    ],
}

DAY_NAMES = tuple(ROUTINE.keys())
RECOVERY_OPTIONS = ("Riposo attivo", "Recupero")

app = Flask(__name__)
app.secret_key = os.environ.get("TRX_SECRET_KEY", "trx-training-tracker-local-key")

PIN_SETTING_KEY = "app_pin_hash"
DEFAULT_PIN = os.environ.get("TRX_APP_PIN", "1234")


def unique_exercises() -> list[str]:
    configured = get_configured_routine()
    names: list[str] = []
    for day_exercises in configured.values():
        for exercise in day_exercises:
            if exercise not in names:
                names.append(exercise)

    if names:
        return names

    for day_exercises in ROUTINE.values():
        for exercise in day_exercises:
            if exercise not in names:
                names.append(exercise)
    return names


def get_configured_routine() -> dict[str, list[str]]:
    routine = {day: [] for day in DAY_NAMES}
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT day_name, exercise_name
            FROM routine_exercises
            ORDER BY day_name, position, id
            """
        ).fetchall()
    for row in rows:
        if row["day_name"] in routine:
            routine[row["day_name"]].append(row["exercise_name"])
    return routine


def get_configured_routine_exercises() -> list[str]:
    routine = get_configured_routine()
    return list(dict.fromkeys(name for exercises in routine.values() for name in exercises))


def ensure_default_routine(conn: sqlite3.Connection) -> None:
    configured_count = conn.execute("SELECT COUNT(*) AS c FROM routine_exercises").fetchone()["c"]
    if configured_count:
        return
    conn.executemany(
        """
        INSERT INTO routine_exercises (day_name, exercise_name, position)
        VALUES (?, ?, ?)
        """,
        (
            (day_name, exercise_name, position)
            for day_name, exercises in ROUTINE.items()
            for position, exercise_name in enumerate(exercises)
        ),
    )


def is_routine_exercise(exercise_name: str) -> bool:
    return exercise_name in unique_exercises()


def get_today_day_name() -> str:
    day_map = {
        0: "Lunedi",
        1: "Martedi",
        2: "Mercoledi",
        3: "Giovedi",
        4: "Venerdi",
        5: "Sabato",
        6: "Domenica",
    }
    return day_map[date.today().weekday()]


def is_allowed_file(filename: str, allowed_extensions: set[str]) -> bool:
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in allowed_extensions


def save_uploaded_file(file_obj, destination_dir: Path) -> str:
    original_name = secure_filename(file_obj.filename or "")
    ext = ""
    if "." in original_name:
        ext = "." + original_name.rsplit(".", 1)[1].lower()
    saved_name = f"{uuid4().hex}{ext}"
    destination = destination_dir / saved_name
    file_obj.save(destination)
    return saved_name


def ensure_wiki_row(conn: sqlite3.Connection, exercise_name: str) -> None:
    conn.execute(
        """
        INSERT INTO exercise_wiki (exercise_name, description, personal_comment, wiki)
        VALUES (?, '', '', 1)
        ON CONFLICT(exercise_name) DO NOTHING
        """,
        (exercise_name,),
    )


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    PHOTO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        wiki_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(exercise_wiki)").fetchall()
        }
        if "wiki" not in wiki_columns:
            conn.execute(
                "ALTER TABLE exercise_wiki ADD COLUMN wiki INTEGER NOT NULL DEFAULT 1 CHECK (wiki IN (0, 1))"
            )
        conn.execute(
            "UPDATE exercise_wiki SET wiki = 1 WHERE exercise_name IN ({})".format(
                ",".join("?" * len(unique_exercises()))
            ),
            tuple(unique_exercises()),
        )
        pin_row = conn.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key = ?",
            (PIN_SETTING_KEY,),
        ).fetchone()
        if pin_row is None:
            conn.execute(
                "INSERT INTO app_settings (setting_key, setting_value) VALUES (?, ?)",
                (PIN_SETTING_KEY, generate_password_hash(DEFAULT_PIN)),
            )
            conn.commit()
        ensure_default_routine(conn)
        conn.executemany(
            """
            INSERT INTO exercise_wiki (exercise_name, description, personal_comment, wiki)
            VALUES (?, '', '', 1)
            ON CONFLICT(exercise_name) DO NOTHING
            """,
            ((exercise_name,) for exercise_name in unique_exercises()),
        )
        configured_names = conn.execute(
            "SELECT DISTINCT exercise_name FROM routine_exercises"
        ).fetchall()
        conn.executemany(
            """
            INSERT INTO exercise_wiki (exercise_name, description, personal_comment, wiki)
            VALUES (?, '', '', 0)
            ON CONFLICT(exercise_name) DO NOTHING
            """,
            ((row["exercise_name"],) for row in configured_names),
        )
        conn.commit()


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapped


def _safe_home_redirect():
    if session.get("authenticated"):
        return redirect(url_for("index"))
    return redirect(url_for("login"))


@app.errorhandler(404)
def handle_not_found(_error):
    return _safe_home_redirect()


@app.errorhandler(405)
def handle_method_not_allowed(_error):
    return _safe_home_redirect()


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pin_input = request.form.get("pin", "").strip()
        with get_db() as conn:
            row = conn.execute(
                "SELECT setting_value FROM app_settings WHERE setting_key = ?",
                (PIN_SETTING_KEY,),
            ).fetchone()

        if row and check_password_hash(row["setting_value"], pin_input):
            session["authenticated"] = True
            return redirect(url_for("index"))

        flash("PIN non valido.")

    return render_template("login.html")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    routine = get_configured_routine()
    with get_db() as conn:
        workout_logs = conn.execute(
            """
            SELECT id, workout_date, day_name, exercise, sets_completed, reps_completed,
                   (sets_completed * reps_completed) AS total_reps, notes
            FROM workout_logs
            ORDER BY workout_date DESC, id DESC
            LIMIT 50
            """
        ).fetchall()

        weekly_metrics = conn.execute(
            """
            SELECT id, week_start, weight_kg, height_cm, notes
            FROM weekly_metrics
            ORDER BY week_start DESC
            LIMIT 20
            """
        ).fetchall()

        stats = conn.execute(
            """
            SELECT
                COUNT(DISTINCT workout_date) AS total_sessions,
                COALESCE(SUM(sets_completed * reps_completed), 0) AS total_reps
            FROM workout_logs
            """
        ).fetchone()

    return render_template(
        "index.html",
        today=date.today().isoformat(),
        routine=routine,
        workout_logs=workout_logs,
        weekly_metrics=weekly_metrics,
        total_sessions=stats["total_sessions"],
        total_reps=stats["total_reps"],
    )


@app.get("/wiki")
@login_required
def wiki_index():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT exercise_name,
                   COALESCE(description, '') AS description,
                   COALESCE(personal_comment, '') AS personal_comment
            FROM exercise_wiki
            WHERE wiki = 1
            ORDER BY exercise_name
            """
        ).fetchall()
        media_counts = conn.execute(
            """
            SELECT exercise_name,
                   SUM(CASE WHEN media_type = 'photo' THEN 1 ELSE 0 END) AS photo_count,
                   SUM(CASE WHEN media_type = 'video_link' THEN 1 ELSE 0 END) AS link_count,
                   SUM(CASE WHEN media_type = 'video_file' THEN 1 ELSE 0 END) AS file_video_count
            FROM exercise_media
            GROUP BY exercise_name
            """
        ).fetchall()

    exercises = [row["exercise_name"] for row in rows]
    row_map = {row["exercise_name"]: row for row in rows}
    count_map = {
        row["exercise_name"]: {
            "photo_count": row["photo_count"] or 0,
            "link_count": row["link_count"] or 0,
            "file_video_count": row["file_video_count"] or 0,
        }
        for row in media_counts
    }

    wiki_cards = []
    for exercise in exercises:
        row = row_map.get(exercise)
        counts = count_map.get(exercise, {"photo_count": 0, "link_count": 0, "file_video_count": 0})
        wiki_cards.append(
            {
                "exercise_name": exercise,
                "description": row["description"] if row else "",
                "personal_comment": row["personal_comment"] if row else "",
                **counts,
            }
        )

    return render_template(
        "wiki_index.html",
        wiki_cards=wiki_cards,
        routine_exercises=set(get_configured_routine_exercises()),
    )


@app.get("/configurazione")
@login_required
def routine_config():
    routine = get_configured_routine()
    with get_db() as conn:
        catalog_rows = conn.execute(
            """
            SELECT exercise_name, wiki, description
            FROM exercise_wiki
            ORDER BY exercise_name
            """
        ).fetchall()
    configured_names = get_configured_routine_exercises()
    catalog_names = [row["exercise_name"] for row in catalog_rows]
    catalog_names.extend(name for name in configured_names if name not in catalog_names)
    return render_template(
        "routine_config.html",
        routine=routine,
        day_names=DAY_NAMES,
        catalog_rows=catalog_rows,
        configured_names=set(configured_names),
        recovery_options=RECOVERY_OPTIONS,
    )


@app.post("/configurazione")
@login_required
def save_routine_config():
    try:
        row_count = int(request.form.get("row_count", "0"))
    except ValueError:
        flash("Configurazione non valida.")
        return redirect(url_for("routine_config"))

    exercises_by_old_name: dict[str, dict[str, object]] = {}
    final_names: set[str] = set()
    for index in range(row_count):
        old_name = request.form.get(f"old_name_{index}", "").strip()
        new_name = request.form.get(f"exercise_name_{index}", "").strip()
        if not old_name or not new_name:
            continue
        if request.form.get(f"remove_{index}") == "1":
            continue
        if new_name in final_names:
            flash("I nomi degli esercizi devono essere univoci.")
            return redirect(url_for("routine_config"))
        final_names.add(new_name)
        exercises_by_old_name[old_name] = {
            "new_name": new_name,
            "wiki": request.form.get(f"wiki_{index}") == "1",
            "days": {
                day_name
                for day_name in DAY_NAMES
                if request.form.get(f"day_{index}_{day_name}") == "1"
            },
        }

    new_name = request.form.get("new_exercise_name", "").strip()
    if new_name:
        if new_name in final_names:
            flash("Esiste già un esercizio con questo nome.")
            return redirect(url_for("routine_config"))
        final_names.add(new_name)
        exercises_by_old_name[new_name] = {
            "new_name": new_name,
            "wiki": request.form.get("new_exercise_wiki") == "1",
            "days": {
                day_name
                for day_name in DAY_NAMES
                if request.form.get(f"new_day_{day_name}") == "1"
            },
        }

    with get_db() as conn:
        existing_rows = conn.execute(
            "SELECT exercise_name, description, personal_comment FROM exercise_wiki"
        ).fetchall()
        existing_names = {row["exercise_name"] for row in existing_rows}
        for old_name, item in exercises_by_old_name.items():
            replacement = item["new_name"]
            if old_name != replacement and replacement in existing_names:
                flash(f"Esiste già un esercizio con il nome {replacement}.")
                return redirect(url_for("routine_config"))
            if old_name != replacement:
                conn.execute(
                    """
                    UPDATE exercise_wiki
                    SET exercise_name = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE exercise_name = ?
                    """,
                    (replacement, old_name),
                )
                conn.execute(
                    "UPDATE exercise_media SET exercise_name = ? WHERE exercise_name = ?",
                    (replacement, old_name),
                )
                conn.execute(
                    "UPDATE workout_completion SET exercise_name = ? WHERE exercise_name = ?",
                    (replacement, old_name),
                )
                conn.execute(
                    "UPDATE workout_logs SET exercise = ? WHERE exercise = ?",
                    (replacement, old_name),
                )
        for old_name, item in exercises_by_old_name.items():
            replacement = item["new_name"]
            conn.execute(
                """
                INSERT INTO exercise_wiki (exercise_name, description, personal_comment, wiki)
                VALUES (?, '', '', ?)
                ON CONFLICT(exercise_name) DO UPDATE SET wiki = excluded.wiki
                """,
                (replacement, int(item["wiki"])),
            )
        conn.execute("DELETE FROM routine_exercises")
        if exercises_by_old_name:
            for day_name in DAY_NAMES:
                day_items = [
                    item["new_name"]
                    for item in exercises_by_old_name.values()
                    if day_name in item["days"]
                ]
                conn.execute("DELETE FROM routine_exercises WHERE day_name = ?", (day_name,))
                conn.executemany(
                    "INSERT INTO routine_exercises (day_name, exercise_name, position) VALUES (?, ?, ?)",
                    ((day_name, name, position) for position, name in enumerate(day_items)),
                )
        retained_names = {item["new_name"] for item in exercises_by_old_name.values()}
        removed_names = existing_names - set(exercises_by_old_name)
        for removed_name in removed_names:
            conn.execute("DELETE FROM exercise_media WHERE exercise_name = ?", (removed_name,))
            conn.execute("DELETE FROM workout_completion WHERE exercise_name = ?", (removed_name,))
            conn.execute("DELETE FROM workout_logs WHERE exercise = ?", (removed_name,))
        conn.execute(
            "DELETE FROM exercise_wiki WHERE exercise_name NOT IN ({})".format(
                ",".join("?" * len(retained_names)) if retained_names else "''"
            ),
            tuple(retained_names),
        )
        conn.commit()

    flash("Configurazione della routine salvata.")
    return redirect(url_for("routine_config"))


@app.get("/wiki/exercise")
@login_required
def wiki_exercise():
    exercise_name = request.args.get("name", "").strip()
    if not exercise_name:
        flash("Seleziona un esercizio dalla Wiki.")
        return redirect(url_for("wiki_index"))

    with get_db() as conn:
        ensure_wiki_row(conn, exercise_name)
        conn.commit()

        wiki = conn.execute(
            """
            SELECT exercise_name, COALESCE(description, '') AS description,
                   COALESCE(personal_comment, '') AS personal_comment, wiki
            FROM exercise_wiki
            WHERE exercise_name = ?
            """,
            (exercise_name,),
        ).fetchone()
        if wiki is None or not wiki["wiki"]:
            flash("La scheda Wiki non è attiva per questo esercizio.")
            return redirect(url_for("wiki_index"))

        media = conn.execute(
            """
            SELECT id, media_type, media_path, COALESCE(title, '') AS title
            FROM exercise_media
            WHERE exercise_name = ?
            ORDER BY id DESC
            """,
            (exercise_name,),
        ).fetchall()

    photos = [m for m in media if m["media_type"] == "photo"]
    video_links = [m for m in media if m["media_type"] == "video_link"]
    video_files = [m for m in media if m["media_type"] == "video_file"]

    return render_template(
        "wiki_exercise.html",
        exercise_name=exercise_name,
        wiki=wiki,
        photos=photos,
        video_links=video_links,
        video_files=video_files,
        max_photos_reached=len(photos) >= 4,
        routine_exercises=set(unique_exercises()),
    )


@app.post("/wiki/exercise/save")
@login_required
def wiki_save_exercise():
    exercise_name = request.form.get("exercise_name", "").strip()
    description = request.form.get("description", "").strip()
    personal_comment = request.form.get("personal_comment", "").strip()

    if not exercise_name:
        return redirect(url_for("wiki_index"))

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO exercise_wiki (exercise_name, description, personal_comment, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(exercise_name) DO UPDATE SET
                description = excluded.description,
                personal_comment = excluded.personal_comment,
                updated_at = CURRENT_TIMESTAMP
            """,
            (exercise_name, description, personal_comment),
        )
        conn.commit()

    flash("Scheda esercizio aggiornata.")
    return redirect(url_for("wiki_exercise", name=exercise_name))


@app.post("/wiki/exercise/add")
@login_required
def wiki_add_exercise():
    exercise_name = request.form.get("exercise_name", "").strip()

    if not exercise_name:
        flash("Inserisci il nome dell'esercizio.")
        return redirect(url_for("wiki_index"))

    if is_routine_exercise(exercise_name):
        flash("Questo esercizio è già presente nella Wiki.")
        return redirect(url_for("wiki_index"))

    with get_db() as conn:
        existing = conn.execute(
            "SELECT 1 FROM exercise_wiki WHERE exercise_name = ?",
            (exercise_name,),
        ).fetchone()
        if existing is not None:
            flash("Esiste già una scheda con questo nome.")
            return redirect(url_for("wiki_index"))

        conn.execute(
            """
            INSERT INTO exercise_wiki (exercise_name, description, personal_comment, updated_at)
            VALUES (?, '', '', CURRENT_TIMESTAMP)
            """,
            (exercise_name,),
        )
        conn.commit()

    flash("Esercizio aggiunto alla Wiki.")
    return redirect(url_for("wiki_exercise", name=exercise_name))


@app.post("/wiki/exercise/rename")
@login_required
def wiki_rename_exercise():
    current_name = request.form.get("current_name", "").strip()
    new_name = request.form.get("new_name", "").strip()

    if not current_name or not new_name:
        flash("Il nome dell'esercizio non può essere vuoto.")
        return redirect(url_for("wiki_index"))
    if current_name == new_name:
        return redirect(url_for("wiki_exercise", name=current_name))
    if is_routine_exercise(current_name):
        flash("Gli esercizi della routine non possono essere rinominati.")
        return redirect(url_for("wiki_exercise", name=current_name))
    if is_routine_exercise(new_name):
        flash("Esiste già un esercizio della routine con questo nome.")
        return redirect(url_for("wiki_exercise", name=current_name))

    with get_db() as conn:
        existing = conn.execute(
            "SELECT 1 FROM exercise_wiki WHERE exercise_name = ?",
            (current_name,),
        ).fetchone()
        if existing is None:
            flash("Scheda esercizio non trovata.")
            return redirect(url_for("wiki_index"))

        duplicate = conn.execute(
            "SELECT 1 FROM exercise_wiki WHERE exercise_name = ?",
            (new_name,),
        ).fetchone()
        if duplicate is not None:
            flash("Esiste già una scheda con questo nome.")
            return redirect(url_for("wiki_exercise", name=current_name))

        wiki = conn.execute(
            "SELECT description, personal_comment FROM exercise_wiki WHERE exercise_name = ?",
            (current_name,),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO exercise_wiki (exercise_name, description, personal_comment, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (new_name, wiki["description"], wiki["personal_comment"]),
        )
        conn.execute(
            "UPDATE exercise_media SET exercise_name = ? WHERE exercise_name = ?",
            (new_name, current_name),
        )
        conn.execute(
            "UPDATE workout_completion SET exercise_name = ? WHERE exercise_name = ?",
            (new_name, current_name),
        )
        conn.execute(
            "UPDATE workout_logs SET exercise = ? WHERE exercise = ?",
            (new_name, current_name),
        )
        conn.execute(
            "UPDATE routine_exercises SET exercise_name = ? WHERE exercise_name = ?",
            (new_name, current_name),
        )
        conn.execute("DELETE FROM exercise_wiki WHERE exercise_name = ?", (current_name,))
        conn.commit()

    flash("Esercizio rinominato.")
    return redirect(url_for("wiki_exercise", name=new_name))


@app.post("/wiki/exercise/delete")
@login_required
def wiki_delete_exercise():
    exercise_name = request.form.get("exercise_name", "").strip()

    if not exercise_name:
        return redirect(url_for("wiki_index"))
    if is_routine_exercise(exercise_name):
        flash("Gli esercizi della routine non possono essere eliminati.")
        return redirect(url_for("wiki_exercise", name=exercise_name))

    with get_db() as conn:
        existing = conn.execute(
            "SELECT 1 FROM exercise_wiki WHERE exercise_name = ?",
            (exercise_name,),
        ).fetchone()
        if existing is None:
            flash("Scheda esercizio non trovata.")
            return redirect(url_for("wiki_index"))

        conn.execute("DELETE FROM exercise_media WHERE exercise_name = ?", (exercise_name,))
        conn.execute("DELETE FROM workout_completion WHERE exercise_name = ?", (exercise_name,))
        conn.execute("DELETE FROM routine_exercises WHERE exercise_name = ?", (exercise_name,))
        conn.execute("DELETE FROM exercise_wiki WHERE exercise_name = ?", (exercise_name,))
        conn.commit()

    flash("Esercizio eliminato dalla Wiki.")
    return redirect(url_for("wiki_index"))


@app.post("/wiki/exercise/upload_photo")
@login_required
def wiki_upload_photo():
    exercise_name = request.form.get("exercise_name", "").strip()
    title = request.form.get("title", "").strip()
    photo = request.files.get("photo")

    if not exercise_name:
        return redirect(url_for("wiki_index"))
    if photo is None or not photo.filename:
        flash("Seleziona una foto da caricare.")
        return redirect(url_for("wiki_exercise", name=exercise_name))
    if not is_allowed_file(photo.filename, ALLOWED_IMAGE_EXTENSIONS):
        flash("Formato foto non supportato.")
        return redirect(url_for("wiki_exercise", name=exercise_name))

    with get_db() as conn:
        ensure_wiki_row(conn, exercise_name)
        photo_count = conn.execute(
            "SELECT COUNT(*) AS c FROM exercise_media WHERE exercise_name = ? AND media_type = 'photo'",
            (exercise_name,),
        ).fetchone()["c"]
        if photo_count >= 4:
            flash("Puoi associare massimo 4 foto per esercizio.")
            return redirect(url_for("wiki_exercise", name=exercise_name))

        saved_name = save_uploaded_file(photo, PHOTO_UPLOAD_DIR)
        conn.execute(
            """
            INSERT INTO exercise_media (exercise_name, media_type, media_path, title)
            VALUES (?, 'photo', ?, ?)
            """,
            (exercise_name, saved_name, title),
        )
        conn.commit()

    flash("Foto caricata.")
    return redirect(url_for("wiki_exercise", name=exercise_name))


@app.post("/wiki/exercise/upload_video_file")
@login_required
def wiki_upload_video_file():
    exercise_name = request.form.get("exercise_name", "").strip()
    title = request.form.get("title", "").strip()
    video_file = request.files.get("video_file")

    if not exercise_name:
        return redirect(url_for("wiki_index"))
    if video_file is None or not video_file.filename:
        flash("Seleziona un video da caricare.")
        return redirect(url_for("wiki_exercise", name=exercise_name))
    if not is_allowed_file(video_file.filename, ALLOWED_VIDEO_EXTENSIONS):
        flash("Formato video non supportato.")
        return redirect(url_for("wiki_exercise", name=exercise_name))

    with get_db() as conn:
        ensure_wiki_row(conn, exercise_name)
        saved_name = save_uploaded_file(video_file, VIDEO_UPLOAD_DIR)
        conn.execute(
            """
            INSERT INTO exercise_media (exercise_name, media_type, media_path, title)
            VALUES (?, 'video_file', ?, ?)
            """,
            (exercise_name, saved_name, title),
        )
        conn.commit()

    flash("Video locale caricato in video_esplicativi.")
    return redirect(url_for("wiki_exercise", name=exercise_name))


@app.post("/wiki/exercise/add_video_link")
@login_required
def wiki_add_video_link():
    exercise_name = request.form.get("exercise_name", "").strip()
    title = request.form.get("title", "").strip()
    video_url = request.form.get("video_url", "").strip()

    if not exercise_name or not video_url:
        flash("Inserisci URL video valido.")
        return redirect(url_for("wiki_exercise", name=exercise_name))

    with get_db() as conn:
        ensure_wiki_row(conn, exercise_name)
        conn.execute(
            """
            INSERT INTO exercise_media (exercise_name, media_type, media_path, title)
            VALUES (?, 'video_link', ?, ?)
            """,
            (exercise_name, video_url, title),
        )
        conn.commit()

    flash("Link video aggiunto.")
    return redirect(url_for("wiki_exercise", name=exercise_name))


@app.post("/wiki/media/update/<int:media_id>")
@login_required
def wiki_update_media(media_id: int):
    title = request.form.get("title", "").strip()
    media_path = request.form.get("media_path", "").strip()

    with get_db() as conn:
        media = conn.execute(
            "SELECT exercise_name, media_type FROM exercise_media WHERE id = ?",
            (media_id,),
        ).fetchone()
        if media is None:
            return redirect(url_for("wiki_index"))

        if media["media_type"] == "video_link":
            if not media_path:
                flash("Il link video non puo essere vuoto.")
                return redirect(url_for("wiki_exercise", name=media["exercise_name"]))
            conn.execute(
                "UPDATE exercise_media SET title = ?, media_path = ? WHERE id = ?",
                (title, media_path, media_id),
            )
        else:
            conn.execute("UPDATE exercise_media SET title = ? WHERE id = ?", (title, media_id))
        conn.commit()

    flash("Contenuto aggiornato.")
    return redirect(url_for("wiki_exercise", name=media["exercise_name"]))


@app.post("/wiki/media/replace_file/<int:media_id>")
@login_required
def wiki_replace_media_file(media_id: int):
    file_obj = request.files.get("replacement_file")

    with get_db() as conn:
        media = conn.execute(
            "SELECT exercise_name, media_type, media_path FROM exercise_media WHERE id = ?",
            (media_id,),
        ).fetchone()
        if media is None:
            return redirect(url_for("wiki_index"))

        if media["media_type"] not in {"photo", "video_file"}:
            flash("La sostituzione file e disponibile solo per foto/video locali.")
            return redirect(url_for("wiki_exercise", name=media["exercise_name"]))

        if file_obj is None or not file_obj.filename:
            flash("Seleziona un file di sostituzione.")
            return redirect(url_for("wiki_exercise", name=media["exercise_name"]))

        if media["media_type"] == "photo":
            if not is_allowed_file(file_obj.filename, ALLOWED_IMAGE_EXTENSIONS):
                flash("Formato foto non supportato.")
                return redirect(url_for("wiki_exercise", name=media["exercise_name"]))
            target_dir = PHOTO_UPLOAD_DIR
        else:
            if not is_allowed_file(file_obj.filename, ALLOWED_VIDEO_EXTENSIONS):
                flash("Formato video non supportato.")
                return redirect(url_for("wiki_exercise", name=media["exercise_name"]))
            target_dir = VIDEO_UPLOAD_DIR

        new_name = save_uploaded_file(file_obj, target_dir)
        conn.execute("UPDATE exercise_media SET media_path = ? WHERE id = ?", (new_name, media_id))
        conn.commit()

    old_path = target_dir / media["media_path"]
    if old_path.exists():
        old_path.unlink()

    flash("File sostituito.")
    return redirect(url_for("wiki_exercise", name=media["exercise_name"]))


@app.post("/wiki/media/delete/<int:media_id>")
@login_required
def wiki_delete_media(media_id: int):
    with get_db() as conn:
        media = conn.execute(
            "SELECT exercise_name, media_type, media_path FROM exercise_media WHERE id = ?",
            (media_id,),
        ).fetchone()
        if media is None:
            return redirect(url_for("wiki_index"))

        conn.execute("DELETE FROM exercise_media WHERE id = ?", (media_id,))
        conn.commit()

    if media["media_type"] == "photo":
        target = PHOTO_UPLOAD_DIR / media["media_path"]
        if target.exists():
            target.unlink()
    if media["media_type"] == "video_file":
        target = VIDEO_UPLOAD_DIR / media["media_path"]
        if target.exists():
            target.unlink()

    flash("Contenuto eliminato.")
    return redirect(url_for("wiki_exercise", name=media["exercise_name"]))


@app.get("/video_esplicativi/<path:filename>")
@login_required
def serve_local_video(filename: str):
    return send_from_directory(VIDEO_UPLOAD_DIR, filename)


@app.get("/uploads/photos/<path:filename>")
@login_required
def serve_uploaded_photo(filename: str):
    return send_from_directory(PHOTO_UPLOAD_DIR, filename)


@app.get("/workout/today")
@login_required
def workout_today():
    today = date.today().isoformat()
    day_name = get_today_day_name()
    exercises = get_configured_routine().get(day_name, [])

    with get_db() as conn:
        completion_rows = conn.execute(
            """
            SELECT exercise_name, completed
            FROM workout_completion
            WHERE workout_date = ?
            """,
            (today,),
        ).fetchall()
        completion_map = {row["exercise_name"]: bool(row["completed"]) for row in completion_rows}

        media_rows = conn.execute(
            """
            SELECT exercise_name, media_type, media_path, COALESCE(title, '') AS title
            FROM exercise_media
            WHERE exercise_name IN ({})
            ORDER BY id ASC
            """.format(",".join("?" * len(exercises)) if exercises else "''"),
            tuple(exercises) if exercises else tuple(),
        ).fetchall()

    media_by_exercise: dict[str, list[dict[str, str]]] = {}
    for row in media_rows:
        current = media_by_exercise.setdefault(row["exercise_name"], [])
        if row["media_type"] == "video_link":
            current.append(
                {
                    "type": "video_link",
                    "title": row["title"] or "Video link",
                    "url": row["media_path"],
                }
            )
        elif row["media_type"] == "video_file":
            current.append(
                {
                    "type": "video_file",
                    "title": row["title"] or "Video locale",
                    "url": url_for("serve_local_video", filename=row["media_path"]),
                }
            )

    checklist = []
    playlist = []
    for exercise in exercises:
        items = media_by_exercise.get(exercise, [])
        checklist.append(
            {
                "exercise": exercise,
                "completed": completion_map.get(exercise, False),
                "media_count": len(items),
            }
        )
        for media_item in items:
            playlist.append({"exercise": exercise, **media_item})

    return render_template(
        "workout_today.html",
        today=today,
        day_name=day_name,
        checklist=checklist,
        playlist=playlist,
    )


@app.post("/workout/toggle_completion")
@login_required
def workout_toggle_completion():
    exercise_name = request.form.get("exercise_name", "").strip()
    workout_date = request.form.get("workout_date", date.today().isoformat()).strip()
    completed = request.form.get("completed", "0") == "1"

    if not exercise_name:
        return jsonify({"ok": False}), 400

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO workout_completion (workout_date, exercise_name, completed, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(workout_date, exercise_name) DO UPDATE SET
                completed = excluded.completed,
                updated_at = CURRENT_TIMESTAMP
            """,
            (workout_date, exercise_name, int(completed)),
        )
        conn.commit()

    return jsonify({"ok": True, "completed": completed})


@app.post("/add_workout")
@login_required
def add_workout():
    workout_date = request.form.get("workout_date", "").strip()
    day_name = request.form.get("day_name", "").strip()
    exercise = request.form.get("exercise", "").strip()
    notes = request.form.get("notes", "").strip()

    try:
        sets_completed = int(request.form.get("sets_completed", "0"))
        reps_completed = int(request.form.get("reps_completed", "0"))
    except ValueError:
        return redirect(url_for("index"))

    if not workout_date or not day_name or not exercise:
        return redirect(url_for("index"))
    if sets_completed <= 0 or reps_completed <= 0:
        return redirect(url_for("index"))

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO workout_logs
            (workout_date, day_name, exercise, sets_completed, reps_completed, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (workout_date, day_name, exercise, sets_completed, reps_completed, notes),
        )
        conn.commit()

    return redirect(url_for("index"))


@app.post("/update_workout/<int:workout_id>")
@login_required
def update_workout(workout_id: int):
    workout_date = request.form.get("workout_date", "").strip()
    day_name = request.form.get("day_name", "").strip()
    exercise = request.form.get("exercise", "").strip()
    notes_input = request.form.get("notes")

    try:
        sets_completed = int(request.form.get("sets_completed", "0"))
        reps_completed = int(request.form.get("reps_completed", "0"))
    except ValueError:
        return redirect(url_for("index"))

    if not workout_date or not day_name or not exercise:
        return redirect(url_for("index"))
    if sets_completed <= 0 or reps_completed <= 0:
        return redirect(url_for("index"))

    with get_db() as conn:
        existing = conn.execute(
            "SELECT notes FROM workout_logs WHERE id = ?",
            (workout_id,),
        ).fetchone()
        if existing is None:
            return redirect(url_for("index"))

        notes = existing["notes"] if notes_input is None else notes_input.strip()

        conn.execute(
            """
            UPDATE workout_logs
            SET workout_date = ?,
                day_name = ?,
                exercise = ?,
                sets_completed = ?,
                reps_completed = ?,
                notes = ?
            WHERE id = ?
            """,
            (workout_date, day_name, exercise, sets_completed, reps_completed, notes, workout_id),
        )
        conn.commit()

    return redirect(url_for("index"))


@app.post("/delete_workout/<int:workout_id>")
@login_required
def delete_workout(workout_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM workout_logs WHERE id = ?", (workout_id,))
        conn.commit()
    return redirect(url_for("index"))


@app.post("/add_metric")
@login_required
def add_metric():
    week_start = request.form.get("week_start", "").strip()
    notes = request.form.get("metric_notes", "").strip()

    try:
        weight_kg = float(request.form.get("weight_kg", "0"))
        height_cm = float(request.form.get("height_cm", "0"))
    except ValueError:
        return redirect(url_for("index"))

    if not week_start or weight_kg <= 0 or height_cm <= 0:
        return redirect(url_for("index"))

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO weekly_metrics (week_start, weight_kg, height_cm, notes)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(week_start) DO UPDATE SET
                weight_kg = excluded.weight_kg,
                height_cm = excluded.height_cm,
                notes = excluded.notes
            """,
            (week_start, weight_kg, height_cm, notes),
        )
        conn.commit()

    return redirect(url_for("index"))


@app.post("/update_metric/<int:metric_id>")
@login_required
def update_metric(metric_id: int):
    week_start = request.form.get("week_start", "").strip()
    notes_input = request.form.get("notes")

    try:
        weight_kg = float(request.form.get("weight_kg", "0"))
        height_cm = float(request.form.get("height_cm", "0"))
    except ValueError:
        return redirect(url_for("index"))

    if not week_start or weight_kg <= 0 or height_cm <= 0:
        return redirect(url_for("index"))

    with get_db() as conn:
        existing = conn.execute(
            "SELECT notes FROM weekly_metrics WHERE id = ?",
            (metric_id,),
        ).fetchone()
        if existing is None:
            return redirect(url_for("index"))

        notes = existing["notes"] if notes_input is None else notes_input.strip()

        conn.execute(
            """
            UPDATE weekly_metrics
            SET week_start = ?,
                weight_kg = ?,
                height_cm = ?,
                notes = ?
            WHERE id = ?
            """,
            (week_start, weight_kg, height_cm, notes, metric_id),
        )
        conn.commit()

    return redirect(url_for("index"))


@app.post("/delete_metric/<int:metric_id>")
@login_required
def delete_metric(metric_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM weekly_metrics WHERE id = ?", (metric_id,))
        conn.commit()
    return redirect(url_for("index"))


@app.post("/change_pin")
@login_required
def change_pin():
    current_pin = request.form.get("current_pin", "").strip()
    new_pin = request.form.get("new_pin", "").strip()

    if len(new_pin) < 4 or not new_pin.isdigit():
        flash("Il nuovo PIN deve contenere almeno 4 cifre numeriche.")
        return redirect(url_for("index"))

    with get_db() as conn:
        row = conn.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key = ?",
            (PIN_SETTING_KEY,),
        ).fetchone()

        if row is None or not check_password_hash(row["setting_value"], current_pin):
            flash("PIN attuale non corretto.")
            return redirect(url_for("index"))

        conn.execute(
            "UPDATE app_settings SET setting_value = ? WHERE setting_key = ?",
            (generate_password_hash(new_pin), PIN_SETTING_KEY),
        )
        conn.commit()

    flash("PIN aggiornato con successo.")
    return redirect(url_for("index"))


@app.get("/api/dashboard")
@login_required
def dashboard_data():
    with get_db() as conn:
        reps_data = conn.execute(
            """
            SELECT workout_date, SUM(sets_completed * reps_completed) AS total_reps
            FROM workout_logs
            GROUP BY workout_date
            ORDER BY workout_date ASC
            """
        ).fetchall()

        weight_data = conn.execute(
            """
            SELECT week_start, weight_kg
            FROM weekly_metrics
            ORDER BY week_start ASC
            """
        ).fetchall()

    return jsonify(
        {
            "reps": {
                "labels": [row["workout_date"] for row in reps_data],
                "values": [row["total_reps"] for row in reps_data],
            },
            "weight": {
                "labels": [row["week_start"] for row in weight_data],
                "values": [row["weight_kg"] for row in weight_data],
            },
        }
    )


init_db()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
