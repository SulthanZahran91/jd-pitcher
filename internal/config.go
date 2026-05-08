package internal

import (
	"fmt"
	"os"
	"strings"

	"github.com/joho/godotenv"
	"gopkg.in/yaml.v3"
)

// Profile is the user's background data.
type Profile struct {
	Name     string        `yaml:"name"`
	Tagline  string        `yaml:"tagline"`
	Experience []ExpEntry  `yaml:"experience"`
	Projects   []Project   `yaml:"projects"`
	Skills     []SkillCat  `yaml:"skills"`
	Meta       MetaInfo    `yaml:"meta"`
}

type ExpEntry struct {
	Role        string   `yaml:"role"`
	CompanyRef  string   `yaml:"company_ref"`
	Duration    string   `yaml:"duration"`
	Highlights  []string `yaml:"highlights"`
}

type Project struct {
	Name        string `yaml:"name"`
	URL         string `yaml:"url"`
	Description string `yaml:"description"`
}

type SkillCat struct {
	Category string   `yaml:"category"`
	Items    []string `yaml:"items"`
}

type MetaInfo struct {
	Interests  []string `yaml:"interests"`
	Location   string   `yaml:"location"`
	VisaStatus string   `yaml:"visa_status"`
}

// Masks maps entity keys to anonymized strings.
type Masks struct {
	Entities map[string]string `yaml:"entities"`
}

// Config holds all runtime configuration.
type Config struct {
	Port            string
	LLMBaseURL      string
	LLMAPIKey       string
	LLMModel        string
	LLMMaxTokens    int
	LLMTemperature  float64
	RateLimitIPHour int
	RateLimitGlobal int
	MaxJDLength     int
	LogDBPath       string
	Profile         Profile
	Masks           Masks
	PromptTemplate  string
}

// LoadConfig reads .env and all YAML/MD files under ./config.
func LoadConfig() (*Config, error) {
	_ = godotenv.Load(".env")

	cfg := &Config{
		Port:            getEnv("PORT", "8080"),
		LLMBaseURL:      getEnv("LLM_BASE_URL", "https://api.deepseek.com/v1"),
		LLMAPIKey:       getEnv("LLM_API_KEY", ""),
		LLMModel:        getEnv("LLM_MODEL", "deepseek-chat"),
		LLMMaxTokens:    getEnvInt("LLM_MAX_TOKENS", 600),
		LLMTemperature:  getEnvFloat("LLM_TEMPERATURE", 0.6),
		RateLimitIPHour: getEnvInt("RATE_LIMIT_IP_HOUR", 5),
		RateLimitGlobal: getEnvInt("RATE_LIMIT_GLOBAL_DAY", 50),
		MaxJDLength:     getEnvInt("MAX_JD_LENGTH", 8000),
		LogDBPath:       getEnv("LOG_DB_PATH", "data/logs.sqlite"),
	}

	// Load profile.yaml
	if err := loadYAML("config/profile.yaml", &cfg.Profile); err != nil {
		return nil, fmt.Errorf("profile.yaml: %w", err)
	}

	// Load masks.yaml
	if err := loadYAML("config/masks.yaml", &cfg.Masks); err != nil {
		return nil, fmt.Errorf("masks.yaml: %w", err)
	}

	// Validate that every company_ref has a mask
	for _, exp := range cfg.Profile.Experience {
		if exp.CompanyRef == "" {
			continue
		}
		if _, ok := cfg.Masks.Entities[exp.CompanyRef]; !ok {
			return nil, fmt.Errorf(
				"missing mask for company_ref %q (add it to config/masks.yaml)",
				exp.CompanyRef,
			)
		}
	}

	// Load prompt.md
	promptBytes, err := os.ReadFile("config/prompt.md")
	if err != nil {
		return nil, fmt.Errorf("prompt.md: %w", err)
	}
	cfg.PromptTemplate = string(promptBytes)

	return cfg, nil
}

func loadYAML(path string, out any) error {
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return yaml.Unmarshal(b, out)
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func getEnvInt(key string, fallback int) int {
	s := os.Getenv(key)
	if s == "" {
		return fallback
	}
	var v int
	_, err := fmt.Sscanf(s, "%d", &v)
	if err != nil {
		return fallback
	}
	return v
}

func getEnvFloat(key string, fallback float64) float64 {
	s := os.Getenv(key)
	if s == "" {
		return fallback
	}
	var v float64
	_, err := fmt.Sscanf(s, "%f", &v)
	if err != nil {
		return fallback
	}
	return v
}

// MaskedProfile serializes the profile with company names replaced.
func (c *Config) MaskedProfile() string {
	var b strings.Builder

	b.WriteString(fmt.Sprintf("**%s** — %s\n\n", c.Profile.Name, c.Profile.Tagline))

	if len(c.Profile.Experience) > 0 {
		b.WriteString("## Experience\n")
		for _, exp := range c.Profile.Experience {
			mask := c.Masks.Entities[exp.CompanyRef]
			b.WriteString(fmt.Sprintf("\n**%s** at %s (%s)\n", exp.Role, mask, exp.Duration))
			for _, h := range exp.Highlights {
				b.WriteString(fmt.Sprintf("- %s\n", h))
			}
		}
	}

	if len(c.Profile.Projects) > 0 {
		b.WriteString("\n## Projects\n")
		for _, p := range c.Profile.Projects {
			b.WriteString(fmt.Sprintf("\n**%s** — %s\n", p.Name, p.Description))
		}
	}

	if len(c.Profile.Skills) > 0 {
		b.WriteString("\n## Skills\n")
		for _, cat := range c.Profile.Skills {
			b.WriteString(fmt.Sprintf("\n**%s:** %s\n", cat.Category, strings.Join(cat.Items, ", ")))
		}
	}

	if len(c.Profile.Meta.Interests) > 0 {
		b.WriteString(fmt.Sprintf("\n## Interests\n%s\n", strings.Join(c.Profile.Meta.Interests, ", ")))
	}

	return b.String()
}
