// Package catalogmodel defines the application's canonical display projection.
package catalogmodel

type ImageVariant struct {
	Role     string `json:"role"`
	Path     string `json:"path"`
	Width    int    `json:"width"`
	Height   int    `json:"height"`
	Bytes    int64  `json:"bytes"`
	MIMEType string `json:"mimeType"`
	SHA256   string `json:"sha256"`
}
type Rating struct {
	Kind       string `json:"kind"`
	SourceText string `json:"source_text"`
}
type Wine struct {
	ID                   string         `json:"id"`
	Name                 string         `json:"name"`
	Winery               string         `json:"winery"`
	Year                 int            `json:"year,omitempty"` // 0 is internal unknown; DB stores NULL, API omits.
	Image                string         `json:"image"`
	Description          string         `json:"description"`
	SourceURL            string         `json:"sourceUrl,omitempty"`
	SourceSnapshotDate   string         `json:"sourceSnapshotDate,omitempty"`
	ImageVariants        []ImageVariant `json:"imageVariants,omitempty"`
	Region               []string       `json:"region,omitempty"`
	Grapes               []string       `json:"grapes,omitempty"`
	CategoryAndSweetness string         `json:"categoryAndSweetness,omitempty"`
	Color                string         `json:"color,omitempty"`
	Sugar                string         `json:"sugar,omitempty"`
	AlcoholPercent       *float64       `json:"alcoholPercent,omitempty"`
	AlcoholMinPercent    *float64       `json:"alcoholMinPercent,omitempty"`
	AlcoholMaxPercent    *float64       `json:"alcoholMaxPercent,omitempty"`
	VolumeL              *float64       `json:"volumeL,omitempty"`
	Ratings              []Rating       `json:"ratings,omitempty"`
}
