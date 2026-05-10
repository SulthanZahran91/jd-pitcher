package internal

import (
	"crypto/sha256"
	"database/sql"
	"fmt"
	"time"

	_ "modernc.org/sqlite"
)

// Logger writes anonymized usage records to SQLite.
type Logger struct {
	db *sql.DB
}

func NewLogger(dbPath string) (*Logger, error) {
	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return nil, err
	}
	if err := db.Ping(); err != nil {
		return nil, err
	}
	schema := `CREATE TABLE IF NOT EXISTS requests (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
		ip_hash TEXT NOT NULL,
		jd_length INTEGER,
		jd_prefix TEXT,
		jd_text TEXT,
		pitch_text TEXT,
		model_used TEXT,
		status TEXT
	);`
	if _, err := db.Exec(schema); err != nil {
		return nil, err
	}
	if err := ensureColumn(db, "jd_text", "TEXT"); err != nil {
		return nil, err
	}
	if err := ensureColumn(db, "pitch_text", "TEXT"); err != nil {
		return nil, err
	}
	return &Logger{db: db}, nil
}

func ensureColumn(db *sql.DB, name, typ string) error {
	rows, err := db.Query(`PRAGMA table_info(requests)`)
	if err != nil {
		return err
	}
	defer rows.Close()

	for rows.Next() {
		var cid int
		var colName, colType string
		var notNull int
		var defaultValue any
		var pk int
		if err := rows.Scan(&cid, &colName, &colType, &notNull, &defaultValue, &pk); err != nil {
			return err
		}
		if colName == name {
			return nil
		}
	}
	if err := rows.Err(); err != nil {
		return err
	}
	_, err = db.Exec(fmt.Sprintf(`ALTER TABLE requests ADD COLUMN %s %s`, name, typ))
	return err
}

func hashIP(ip string) string {
	salt := time.Now().UTC().Format("2006-01-02")
	h := sha256.Sum256([]byte(ip + salt))
	return fmt.Sprintf("%x", h)
}

func (l *Logger) Log(ip string, jd string, pitch string, model, status string) error {
	prefix := jd
	if len(prefix) > 80 {
		prefix = prefix[:80]
	}
	_, err := l.db.Exec(
		`INSERT INTO requests (ip_hash, jd_length, jd_prefix, jd_text, pitch_text, model_used, status) VALUES (?, ?, ?, ?, ?, ?, ?)`,
		hashIP(ip), len(jd), prefix, jd, pitch, model, status,
	)
	return err
}

func (l *Logger) Close() error {
	return l.db.Close()
}
