package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"html/template"
	"log"
	"net"
	"net/http"
	"strings"

	"github.com/SulthanZahran91/jd-pitcher/internal"
	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
)

type PitchRequest struct {
	JD string `json:"jd"`
}

type PitchResponse struct {
	Pitch     string `json:"pitch"`
	ModelUsed string `json:"model_used"`
	Cached    bool   `json:"cached"`
}

type ResultData struct {
	Name      string
	PitchHTML template.HTML
}

func main() {
	cfg, err := internal.LoadConfig()
	if err != nil {
		log.Fatalf("config load failed: %v", err)
	}

	llm := internal.NewDeepSeekClient(cfg)
	limiter := internal.NewRateLimiter(cfg.RateLimitIPHour, cfg.RateLimitGlobal)
	logger, err := internal.NewLogger(cfg.LogDBPath)
	if err != nil {
		log.Fatalf("logger init failed: %v", err)
	}
	defer logger.Close()

	resultTmpl := template.Must(template.ParseFiles("web/result.tmpl"))

	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(middleware.RealIP)
	r.Use(limiter.Middleware)

	// Static files
	fileServer := http.FileServer(http.Dir("./web"))
	r.Handle("/*", http.StripPrefix("/", fileServer))

	// API: JSON endpoint for agents
	r.Post("/api/pitch", func(w http.ResponseWriter, r *http.Request) {
		var req PitchRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			logAndRespond(w, r, logger, cfg, "invalid JSON", http.StatusBadRequest)
			return
		}
		if len(req.JD) > cfg.MaxJDLength {
			logAndRespond(w, r, logger, cfg, "JD too long", http.StatusBadRequest)
			return
		}
		if len(req.JD) == 0 {
			logAndRespond(w, r, logger, cfg, "JD empty", http.StatusBadRequest)
			return
		}

		pitch, err := generatePitch(cfg, llm, req.JD)
		if err != nil {
			log.Printf("LLM error: %v", err)
			logRequest(r, logger, cfg, req.JD, "error")
			w.WriteHeader(http.StatusInternalServerError)
			json.NewEncoder(w).Encode(map[string]string{"error": "Failed to generate pitch. Please try again later."})
			return
		}

		logRequest(r, logger, cfg, req.JD, "success")
		resp := PitchResponse{
			Pitch:     pitch,
			ModelUsed: cfg.LLMModel,
			Cached:    false,
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	})

	// Form endpoint: returns HTML card
	r.Post("/pitch", func(w http.ResponseWriter, r *http.Request) {
		if err := r.ParseForm(); err != nil {
			logAndRespondHTML(w, r, logger, cfg, "invalid form", http.StatusBadRequest)
			return
		}
		jd := r.FormValue("jd")
		if len(jd) > cfg.MaxJDLength {
			logAndRespondHTML(w, r, logger, cfg, "JD too long", http.StatusBadRequest)
			return
		}
		if len(jd) == 0 {
			logAndRespondHTML(w, r, logger, cfg, "JD empty", http.StatusBadRequest)
			return
		}

		pitch, err := generatePitch(cfg, llm, jd)
		if err != nil {
			log.Printf("LLM error: %v", err)
			logRequest(r, logger, cfg, jd, "error")
			w.WriteHeader(http.StatusInternalServerError)
			fmt.Fprintf(w, "<p>Error generating pitch. Please try again later.</p>")
			return
		}

		logRequest(r, logger, cfg, jd, "success")

		data := ResultData{
			Name:      cfg.Profile.Name,
			PitchHTML: template.HTML(nl2br(template.HTMLEscapeString(pitch))),
		}

		var buf bytes.Buffer
		if err := resultTmpl.Execute(&buf, data); err != nil {
			log.Printf("template error: %v", err)
			http.Error(w, "render error", http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Write(buf.Bytes())
	})

	port := cfg.Port
	log.Printf("jd-pitcher starting on :%s", port)
	if err := http.ListenAndServe(":"+port, r); err != nil {
		log.Fatalf("server failed: %v", err)
	}
}

func generatePitch(cfg *internal.Config, llm *internal.DeepSeekClient, jd string) (string, error) {
	maskedProfile := cfg.MaskedProfile()
	prompt := strings.NewReplacer(
		"{{.Name}}", cfg.Profile.Name,
		"{{.JD}}", jd,
		"{{.MaskedProfile}}", maskedProfile,
	).Replace(cfg.PromptTemplate)

	return llm.Chat(prompt, "")
}

func logAndRespond(w http.ResponseWriter, r *http.Request, logger *internal.Logger, cfg *internal.Config, msg string, code int) {
	logRequest(r, logger, cfg, "", "error")
	http.Error(w, msg, code)
}

func logAndRespondHTML(w http.ResponseWriter, r *http.Request, logger *internal.Logger, cfg *internal.Config, msg string, code int) {
	logRequest(r, logger, cfg, "", "error")
	w.WriteHeader(code)
	fmt.Fprintf(w, "<p>%s</p>", msg)
}

func logRequest(r *http.Request, logger *internal.Logger, cfg *internal.Config, jd, status string) {
	ip, _, _ := net.SplitHostPort(r.RemoteAddr)
	if ip == "" {
		ip = r.RemoteAddr
	}
	if err := logger.Log(ip, jd, cfg.LLMModel, status); err != nil {
		log.Printf("logger error: %v", err)
	}
}

func nl2br(s string) string {
	return strings.ReplaceAll(s, "\n", "<br>\n")
}
