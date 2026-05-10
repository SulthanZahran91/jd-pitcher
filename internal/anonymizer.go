package internal

import (
	"fmt"
	"strings"
)

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

	if c.Profile.Meta.Location != "" {
		b.WriteString(fmt.Sprintf("\n## Location\n%s\n", c.Profile.Meta.Location))
	}

	if c.Profile.Meta.VisaStatus != "" {
		b.WriteString(fmt.Sprintf("\n## Visa Status\n%s\n", c.Profile.Meta.VisaStatus))
	}

	if len(c.Profile.Meta.Interests) > 0 {
		b.WriteString(fmt.Sprintf("\n## Interests\n%s\n", strings.Join(c.Profile.Meta.Interests, ", ")))
	}

	return b.String()
}
