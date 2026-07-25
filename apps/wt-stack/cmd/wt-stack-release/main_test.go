package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestRunPreparesReleaseAndPrintsWorkflowOutputs(t *testing.T) {
	t.Parallel()

	changelog := filepath.Join(t.TempDir(), "CHANGELOG.md")
	if err := os.WriteFile(
		changelog,
		[]byte("# Changelog\n\n## Unreleased\n\n### Added\n\n- Command.\n"),
		0o640,
	); err != nil {
		t.Fatalf("write changelog: %v", err)
	}
	var out bytes.Buffer
	var errOut bytes.Buffer
	code := run(
		[]string{
			"--changelog", changelog,
			"--current-version", "0.3.1",
			"--date", "2026-07-24",
		},
		&out,
		&errOut,
		time.Time{},
	)
	if code != 0 {
		t.Fatalf("exit code = %d, stderr = %s", code, errOut.String())
	}
	if out.String() != "release=true\nversion=0.4.0\nbump=minor\n" {
		t.Fatalf("output = %q", out.String())
	}
	content, err := os.ReadFile(changelog)
	if err != nil {
		t.Fatalf("read changelog: %v", err)
	}
	if !strings.Contains(
		string(content),
		"## 0.4.0 - 2026-07-24",
	) {
		t.Fatalf("changelog was not prepared:\n%s", content)
	}
	info, err := os.Stat(changelog)
	if err != nil {
		t.Fatalf("stat changelog: %v", err)
	}
	if info.Mode().Perm() != 0o640 {
		t.Fatalf("changelog mode = %o, want 640", info.Mode().Perm())
	}
}

func TestRunSkipsEmptyUnreleasedSection(t *testing.T) {
	t.Parallel()

	changelog := filepath.Join(t.TempDir(), "CHANGELOG.md")
	original := []byte("## Unreleased\n\n## 0.3.1\n")
	if err := os.WriteFile(changelog, original, 0o600); err != nil {
		t.Fatalf("write changelog: %v", err)
	}
	var out bytes.Buffer
	var errOut bytes.Buffer
	code := run(
		[]string{
			"--changelog", changelog,
			"--current-version", "0.3.1",
		},
		&out,
		&errOut,
		time.Date(2026, time.July, 24, 0, 0, 0, 0, time.UTC),
	)
	if code != 0 || out.String() != "release=false\n" {
		t.Fatalf(
			"exit code = %d, stdout = %q, stderr = %q",
			code,
			out.String(),
			errOut.String(),
		)
	}
	content, err := os.ReadFile(changelog)
	if err != nil {
		t.Fatalf("read changelog: %v", err)
	}
	if !bytes.Equal(content, original) {
		t.Fatalf("empty release changed the changelog:\n%s", content)
	}
}

func TestRunRejectsInvalidArguments(t *testing.T) {
	t.Parallel()

	tests := [][]string{
		{},
		{"unexpected"},
		{"--current-version", "0.3.1", "--date", "tomorrow"},
	}
	for _, args := range tests {
		var errOut bytes.Buffer
		if code := run(
			args,
			&bytes.Buffer{},
			&errOut,
			time.Time{},
		); code == 0 {
			t.Fatalf("args %v succeeded", args)
		}
	}
}
