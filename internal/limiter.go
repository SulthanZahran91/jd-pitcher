package internal

import (
	"crypto/sha256"
	"fmt"
	"net"
	"net/http"
	"sync"
	"time"
)

// RateLimiter provides per-IP token bucket + global daily cap.
type RateLimiter struct {
	mu sync.RWMutex

	ipHourly   map[string]*bucket
	globalDay  int
	globalDate string

	ipLimit     int
	globalLimit int
}

type bucket struct {
	tokens     float64
	lastRefill time.Time
}

func NewRateLimiter(ipHourly, globalDaily int) *RateLimiter {
	return &RateLimiter{
		ipHourly:    make(map[string]*bucket),
		ipLimit:     ipHourly,
		globalLimit: globalDaily,
		globalDate:  today(),
	}
}

func today() string {
	return time.Now().UTC().Format("2006-01-02")
}

func ipHash(ip string) string {
	salt := today()
	h := sha256.Sum256([]byte(ip + salt))
	return fmt.Sprintf("%x", h[:8])
}

// Middleware returns an http.Handler that enforces rate limits.
func (rl *RateLimiter) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ip, _, err := net.SplitHostPort(r.RemoteAddr)
		if err != nil {
			ip = r.RemoteAddr
		}
		key := ipHash(ip)

		// Check global daily cap
		now := time.Now().UTC()
		date := now.Format("2006-01-02")

		rl.mu.Lock()
		if date != rl.globalDate {
			rl.globalDate = date
			rl.globalDay = 0
		}
		if rl.globalDay >= rl.globalLimit {
			rl.mu.Unlock()
			w.Header().Set("Retry-After", "3600")
			http.Error(w, "Global daily rate limit exceeded", http.StatusTooManyRequests)
			return
		}

		// Check per-IP bucket
		b, ok := rl.ipHourly[key]
		if !ok {
			b = &bucket{tokens: float64(rl.ipLimit), lastRefill: now}
			rl.ipHourly[key] = b
		}

		// Refill: 1 token per (60 / limit) minutes
		elapsed := now.Sub(b.lastRefill)
		refillRate := float64(rl.ipLimit) / 60.0 // tokens per minute
		b.tokens += elapsed.Minutes() * refillRate
		if b.tokens > float64(rl.ipLimit) {
			b.tokens = float64(rl.ipLimit)
		}
		b.lastRefill = now

		if b.tokens < 1 {
			rl.mu.Unlock()
			w.Header().Set("Retry-After", fmt.Sprintf("%d", int(60/rl.ipLimit)+1))
			http.Error(w, "Rate limit exceeded", http.StatusTooManyRequests)
			return
		}

		b.tokens--
		rl.globalDay++
		rl.mu.Unlock()

		next.ServeHTTP(w, r)
	})
}
