package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"

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

func main() {
	cfg, err := internal.LoadConfig()
	if err != nil {
		log.Fatalf("config load failed: %v", err)
	}

	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(middleware.RealIP)

	// Static files
	fileServer := http.FileServer(http.Dir("./web"))
	r.Handle("/*", http.StripPrefix("/", fileServer))

	// API: JSON endpoint for agents
	r.Post("/api/pitch", func(w http.ResponseWriter, r *http.Request) {
		var req PitchRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "invalid JSON", http.StatusBadRequest)
			return
		}
		if len(req.JD) > cfg.MaxJDLength {
			http.Error(w, "JD too long", http.StatusBadRequest)
			return
		}

		// Phase 2: call LLM here
		resp := PitchResponse{
			Pitch:     "[stub] pitch will be generated in Phase 2",
			ModelUsed: cfg.LLMModel,
			Cached:    false,
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	})

	// Form endpoint: returns HTML card
	r.Post("/pitch", func(w http.ResponseWriter, r *http.Request) {
		if err := r.ParseForm(); err != nil {
			http.Error(w, "invalid form", http.StatusBadRequest)
			return
		}
		jd := r.FormValue("jd")
		if len(jd) > cfg.MaxJDLength {
			http.Error(w, "JD too long", http.StatusBadRequest)
			return
		}

		// Phase 2: render result.tmpl here
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		fmt.Fprintf(w, "<!DOCTYPE html><html><head><link rel=\"stylesheet\" href=\"./style.css\"></head><body><article class=\"pitch-card\"><h2>Why %s is a strong fit</h2><p>[stub] pitch will be generated in Phase 2</p></article></body></html>", cfg.Profile.Name)
	})

	port := cfg.Port
	log.Printf("jd-pitcher starting on :%s", port)
	if err := http.ListenAndServe(":"+port, r); err != nil {
		log.Fatalf("server failed: %v", err)
	}
}
