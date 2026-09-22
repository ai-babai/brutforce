package catalogimport

import (
	"strings"
	"testing"
)

func acceptedTestImage(dir string, width, height int) packageImage {
	sha := strings.Repeat("a", 64)
	return packageImage{Path: dir + "/" + sha + ".webp", SHA256: sha, MIMEType: "image/webp", Width: width, Height: height, Bytes: 100}
}

func acceptedTestWine() packageWine {
	master := acceptedTestImage("original", 1000, 500)
	master.Variants = []packageVariant{
		{Role: "thumbnail", packageImage: acceptedTestImage("400", 400, 200)},
		{Role: "card", packageImage: acceptedTestImage("800", 800, 400)},
		{Role: "original", packageImage: acceptedTestImage("original", 1000, 500)},
	}
	return packageWine{ID: "stable-id", Slug: "public-slug", Title: "Wine", Producer: "Cellar", SourceURL: "https://example.test/wine", Image: master, imagePresent: true}
}

func TestAcceptedProjectionRejectsMalformedVariantRatio(t *testing.T) {
	wine := acceptedTestWine()
	wine.Image.Variants[0].Height = 300
	if _, err := acceptedWine(wine); err == nil || !strings.Contains(err.Error(), "aspect ratio") {
		t.Fatalf("malformed ratio was accepted: %v", err)
	}
}

func TestAcceptedProjectionRejectsVariantUpscale(t *testing.T) {
	wine := acceptedTestWine()
	wine.Image.Variants[2].Width = 1200
	if _, err := acceptedWine(wine); err == nil || !strings.Contains(err.Error(), "upscales") {
		t.Fatalf("upscaled variant was accepted: %v", err)
	}
}

func TestAcceptedProjectionCannotRunWithoutAcceptedReport(t *testing.T) {
	if _, _, _, _, err := LoadAcceptedProjection(Options{}, "", "validator"); err == nil {
		t.Fatal("accepted fast path ran without accepted report")
	}
}
