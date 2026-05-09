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
		model_used TEXT,
		status TEXT
	);`
	if _, err := db.Exec(schema); err != nil {
		return nil, err
	}
	return &Logger{db: db}, nil
}

func hashIP(ip string) string {
	salt := time.Now().UTC().Format("2006-01-02")
	h := sha256.Sum256([]byte(ip + salt))
	return fmt.Sprintf("%x", h)
}

func (l *Logger) Log(ip string, jd string, model, status string) error {
	prefix := jd
	if len(prefix) > 80 {
		prefix = prefix[:80]
	}
	_, err := l.db.Exec(
		`INSERT INTO requests (ip_hash, jd_length, jd_prefix, model_used, status) VALUES (?, ?, ?, ?, ?)`,
		hashIP(ip), len(jd), prefix, model, status,
	)
	return err
}

func (l *Logger) Close() error {
	return l.db.Close()
}
