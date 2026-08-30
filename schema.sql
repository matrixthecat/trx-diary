CREATE TABLE IF NOT EXISTS workout_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_date TEXT NOT NULL,
    day_name TEXT NOT NULL,
    exercise TEXT NOT NULL,
    sets_completed INTEGER NOT NULL CHECK (sets_completed > 0),
    reps_completed INTEGER NOT NULL CHECK (reps_completed > 0),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS weekly_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT NOT NULL UNIQUE,
    weight_kg REAL NOT NULL CHECK (weight_kg > 0),
    height_cm REAL NOT NULL CHECK (height_cm > 0),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS app_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS exercise_wiki (
    exercise_name TEXT PRIMARY KEY,
    description TEXT,
    personal_comment TEXT,
    wiki INTEGER NOT NULL DEFAULT 1 CHECK (wiki IN (0, 1)),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS exercise_media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_name TEXT NOT NULL,
    media_type TEXT NOT NULL CHECK (media_type IN ('photo', 'video_link', 'video_file')),
    media_path TEXT NOT NULL,
    title TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (exercise_name) REFERENCES exercise_wiki(exercise_name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS workout_completion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_date TEXT NOT NULL,
    exercise_name TEXT NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1)),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(workout_date, exercise_name)
);

CREATE TABLE IF NOT EXISTS routine_exercises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day_name TEXT NOT NULL,
    exercise_name TEXT NOT NULL,
    position INTEGER NOT NULL,
    UNIQUE(day_name, exercise_name)
);
