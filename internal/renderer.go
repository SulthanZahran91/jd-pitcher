package internal

import (
	"bytes"
	"html/template"
)

// ResultData is passed to the HTML result template.
type ResultData struct {
	Name      string
	PitchHTML template.HTML
}

// RenderResult executes the pitch card template with the given data.
func RenderResult(tmpl *template.Template, data ResultData) ([]byte, error) {
	var buf bytes.Buffer
	if err := tmpl.Execute(&buf, data); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}
