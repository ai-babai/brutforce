package main

import (
	"context"
	"sort"
	"strconv"
	"strings"
	"unicode"
)

// catalogSearchQuery keeps the distinction between an omitted/blank query and
// punctuation-only input. The former lists a catalog; the latter has no words
// to match and must therefore return no records.
type catalogSearchQuery struct {
	blank  bool
	tokens []string
}

type catalogMatchClass uint8

const (
	catalogNoMatch catalogMatchClass = iota
	catalogFuzzyMatch
	catalogPartialMatch
	catalogExactMatch
)

func parseCatalogSearchQuery(raw string) catalogSearchQuery {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return catalogSearchQuery{blank: true}
	}
	return catalogSearchQuery{tokens: catalogSearchTokens(trimmed)}
}

// catalogSearchTokens lower-cases Unicode text, folds Russian ё to е, and uses
// every non-letter/digit rune as a word boundary.
func catalogSearchTokens(value string) []string {
	value = strings.ReplaceAll(strings.ToLower(value), "ё", "е")
	return strings.FieldsFunc(value, func(r rune) bool {
		return !unicode.IsLetter(r) && !unicode.IsDigit(r)
	})
}

func rankWineList(catalog []wine, rawQuery string) []wine {
	result, _ := rankWineListContext(context.Background(), catalog, rawQuery)
	return result
}

func rankWineListContext(ctx context.Context, catalog []wine, rawQuery string) ([]wine, error) {
	query := parseCatalogSearchQuery(rawQuery)
	if query.blank {
		return sortedWines(catalog), nil
	}
	if len(query.tokens) == 0 {
		return []wine{}, nil
	}
	type rankedWine struct {
		wine
		class catalogMatchClass
	}
	ranked := make([]rankedWine, 0, len(catalog))
	for _, item := range catalog {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		class, ok := matchCatalogWine(item, query.tokens)
		if ok {
			ranked = append(ranked, rankedWine{wine: item, class: class})
		}
	}
	sort.Slice(ranked, func(i, j int) bool {
		if ranked[i].class != ranked[j].class {
			return ranked[i].class > ranked[j].class
		}
		return ranked[i].ID < ranked[j].ID
	})
	result := make([]wine, len(ranked))
	for i := range ranked {
		result[i] = ranked[i].wine
	}
	return result, nil
}

func matchCatalogWine(item wine, queryTokens []string) (catalogMatchClass, bool) {
	words := append(catalogSearchTokens(item.Name), catalogSearchTokens(item.Winery)...)
	if item.Year != 0 {
		words = append(words, strconv.Itoa(item.Year))
	}
	lowest := catalogExactMatch
	for _, query := range queryTokens {
		match := matchCatalogToken(query, words)
		if match == catalogNoMatch {
			return catalogNoMatch, false
		}
		if match < lowest {
			lowest = match
		}
	}
	return lowest, true
}

func matchCatalogToken(query string, words []string) catalogMatchClass {
	if numericCatalogToken(query) {
		for _, word := range words {
			if query == word {
				return catalogExactMatch
			}
		}
		return catalogNoMatch
	}
	partial := false
	for _, word := range words {
		if query == word {
			return catalogExactMatch
		}
		if strings.HasPrefix(word, query) {
			partial = true
		}
	}
	if partial {
		return catalogPartialMatch
	}
	if !fuzzyCatalogWord(query) {
		return catalogNoMatch
	}
	for _, word := range words {
		if fuzzyCatalogWord(word) && withinOneEdit(query, word) {
			return catalogFuzzyMatch
		}
	}
	return catalogNoMatch
}

func numericCatalogToken(token string) bool {
	if token == "" {
		return false
	}
	for _, r := range token {
		if !unicode.IsDigit(r) {
			return false
		}
	}
	return true
}

func fuzzyCatalogWord(word string) bool {
	if len([]rune(word)) < 5 {
		return false
	}
	for _, r := range word {
		if !unicode.IsLetter(r) {
			return false
		}
	}
	return true
}

// withinOneEdit accepts one insertion, deletion, substitution, or adjacent
// transposition. Inputs are already constrained to whole alphabetic words.
func withinOneEdit(left, right string) bool {
	a, b := []rune(left), []rune(right)
	if abs(len(a)-len(b)) > 1 {
		return false
	}
	if len(a) == len(b) {
		first := 0
		for first < len(a) && a[first] == b[first] {
			first++
		}
		if first == len(a) {
			return false // exact is classified before this function
		}
		if first+1 < len(a) && a[first] == b[first+1] && a[first+1] == b[first] {
			for i := first + 2; i < len(a); i++ {
				if a[i] != b[i] {
					return false
				}
			}
			return true
		}
		for i := first + 1; i < len(a); i++ {
			if a[i] != b[i] {
				return false
			}
		}
		return true
	}
	if len(a) > len(b) {
		a, b = b, a
	}
	// a is shorter by one rune. Advance around the one inserted rune in b.
	i, j := 0, 0
	skipped := false
	for i < len(a) && j < len(b) {
		if a[i] == b[j] {
			i++
			j++
			continue
		}
		if skipped {
			return false
		}
		skipped = true
		j++
	}
	return true
}

func abs(value int) int {
	if value < 0 {
		return -value
	}
	return value
}
