package release

import (
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"
)

const unreleasedHeading = "## Unreleased"

// ErrNoChanges reports that the Unreleased changelog section is empty.
var ErrNoChanges = errors.New("changelog has no unreleased changes")

// Result contains a prepared changelog and its automatically selected version.
type Result struct {
	Content []byte
	Version string
	Bump    string
}

// Prepare promotes the Unreleased changelog section into a dated release.
func Prepare(
	content []byte,
	currentVersion string,
	releaseDate time.Time,
) (Result, error) {
	lines := strings.Split(
		strings.ReplaceAll(string(content), "\r\n", "\n"),
		"\n",
	)
	unreleasedIndex := -1
	for index, line := range lines {
		if line != unreleasedHeading {
			continue
		}
		if unreleasedIndex >= 0 {
			return Result{}, errors.New(
				"changelog contains multiple Unreleased sections",
			)
		}
		unreleasedIndex = index
	}
	if unreleasedIndex < 0 {
		return Result{}, errors.New(
			"changelog is missing an Unreleased section",
		)
	}
	nextReleaseIndex := len(lines)
	for index := unreleasedIndex + 1; index < len(lines); index++ {
		if strings.HasPrefix(lines[index], "## ") {
			nextReleaseIndex = index
			break
		}
	}
	unreleased := strings.TrimSpace(
		strings.Join(lines[unreleasedIndex+1:nextReleaseIndex], "\n"),
	)
	if unreleased == "" {
		return Result{}, ErrNoChanges
	}

	major, minor, patch, err := parseVersion(currentVersion)
	if err != nil {
		return Result{}, err
	}
	bump := changelogBump(unreleased)
	switch bump {
	case "major":
		major++
		minor = 0
		patch = 0
	case "minor":
		minor++
		patch = 0
	default:
		patch++
	}
	version := fmt.Sprintf("%d.%d.%d", major, minor, patch)

	var prepared strings.Builder
	prepared.WriteString(
		strings.Join(lines[:unreleasedIndex+1], "\n"),
	)
	prepared.WriteString("\n\n## ")
	prepared.WriteString(version)
	prepared.WriteString(" - ")
	prepared.WriteString(releaseDate.Format("2006-01-02"))
	prepared.WriteString("\n\n")
	prepared.WriteString(unreleased)
	if nextReleaseIndex < len(lines) {
		prepared.WriteString("\n\n")
		prepared.WriteString(
			strings.TrimLeft(
				strings.Join(lines[nextReleaseIndex:], "\n"),
				"\n",
			),
		)
	}
	if !strings.HasSuffix(prepared.String(), "\n") {
		prepared.WriteByte('\n')
	}

	return Result{
		Content: []byte(prepared.String()),
		Version: version,
		Bump:    bump,
	}, nil
}

func changelogBump(unreleased string) string {
	bump := "patch"
	for _, line := range strings.Split(unreleased, "\n") {
		heading := strings.ToLower(strings.TrimSpace(line))
		switch {
		case strings.HasPrefix(heading, "### breaking"),
			heading == "### removed":
			return "major"
		case heading == "### added":
			bump = "minor"
		}
	}
	return bump
}

func parseVersion(version string) (int, int, int, error) {
	version = strings.TrimPrefix(strings.TrimSpace(version), "v")
	parts := strings.Split(version, ".")
	if len(parts) != 3 {
		return 0, 0, 0, fmt.Errorf(
			"current version %q is not major.minor.patch",
			version,
		)
	}
	values := make([]int, 3)
	for index, part := range parts {
		value, err := strconv.Atoi(part)
		if err != nil || value < 0 {
			return 0, 0, 0, fmt.Errorf(
				"current version %q is not major.minor.patch",
				version,
			)
		}
		values[index] = value
	}
	return values[0], values[1], values[2], nil
}
