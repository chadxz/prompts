package release

import (
	"errors"
	"strings"
	"testing"
	"time"
)

func TestPrepareSelectsVersionFromChangelogSections(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name        string
		unreleased  string
		wantVersion string
		wantBump    string
	}{
		{
			name:        "fix",
			unreleased:  "### Fixed\n\n- Corrected a defect.",
			wantVersion: "1.2.4",
			wantBump:    "patch",
		},
		{
			name:        "addition",
			unreleased:  "### Added\n\n- Added a command.",
			wantVersion: "1.3.0",
			wantBump:    "minor",
		},
		{
			name: "breaking change",
			unreleased: "### Added\n\n- Added a command.\n\n" +
				"### Breaking changes\n\n- Replaced the state schema.",
			wantVersion: "2.0.0",
			wantBump:    "major",
		},
		{
			name:        "removal",
			unreleased:  "### Removed\n\n- Removed a command.",
			wantVersion: "2.0.0",
			wantBump:    "major",
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()

			input := "# Changelog\n\n## Unreleased\n\n" +
				test.unreleased +
				"\n\n## 1.2.3 - 2026-07-20\n\nPrevious.\n"
			result, err := Prepare(
				[]byte(input),
				"1.2.3",
				time.Date(2026, time.July, 24, 0, 0, 0, 0, time.UTC),
			)
			if err != nil {
				t.Fatalf("prepare: %v", err)
			}
			if result.Version != test.wantVersion ||
				result.Bump != test.wantBump {
				t.Fatalf("result = %#v", result)
			}
			output := string(result.Content)
			if !strings.Contains(
				output,
				"## "+test.wantVersion+" - 2026-07-24\n\n"+
					test.unreleased,
			) {
				t.Fatalf("prepared changelog:\n%s", output)
			}
			if strings.Count(output, "## Unreleased") != 1 ||
				!strings.Contains(output, "## 1.2.3 - 2026-07-20") {
				t.Fatalf("prepared changelog lost history:\n%s", output)
			}
		})
	}
}

func TestPrepareRejectsInvalidInput(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name    string
		content string
		version string
		want    string
		target  error
	}{
		{
			name:    "empty unreleased section",
			content: "## Unreleased\n\n## 1.2.3\n",
			version: "1.2.3",
			target:  ErrNoChanges,
		},
		{
			name:    "missing section",
			content: "## 1.2.3\n",
			version: "1.2.3",
			want:    "missing an Unreleased section",
		},
		{
			name: "duplicate section",
			content: "## Unreleased\n\n### Fixed\n\n- One.\n\n" +
				"## Unreleased\n\n### Fixed\n\n- Two.\n",
			version: "1.2.3",
			want:    "multiple Unreleased sections",
		},
		{
			name:    "invalid version",
			content: "## Unreleased\n\n### Fixed\n\n- One.\n",
			version: "next",
			want:    "not major.minor.patch",
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()

			_, err := Prepare(
				[]byte(test.content),
				test.version,
				time.Now(),
			)
			if test.target != nil {
				if !errors.Is(err, test.target) {
					t.Fatalf("error = %v, want %v", err, test.target)
				}
				return
			}
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("error = %v, want %q", err, test.want)
			}
		})
	}
}
