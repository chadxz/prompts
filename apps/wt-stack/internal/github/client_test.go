package github

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestLinkDelegatesAStackToGhStack(t *testing.T) {
	root := t.TempDir()
	logPath := filepath.Join(root, "gh.log")
	ghPath := filepath.Join(root, "gh")
	script := "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$WT_STACK_TEST_LOG\"\n"
	if err := os.WriteFile(ghPath, []byte(script), 0o755); err != nil {
		t.Fatalf("write fake gh: %v", err)
	}
	t.Setenv("WT_STACK_GH_BIN", ghPath)
	t.Setenv("WT_STACK_TEST_LOG", logPath)

	var output bytes.Buffer
	client := NewClient(root, os.Stdout, os.Stderr)
	client.out = &output
	client.err = &output
	if err := client.Link(
		context.Background(),
		"example/repository",
		"origin",
		"main",
		[]string{"feature-one", "feature-two"},
	); err != nil {
		t.Fatalf("link stack: %v", err)
	}

	logged, err := os.ReadFile(logPath)
	if err != nil {
		t.Fatalf("read fake gh log: %v", err)
	}
	want := "stack link --base main --remote origin feature-one feature-two"
	if got := strings.TrimSpace(string(logged)); got != want {
		t.Fatalf("gh arguments = %q, want %q", got, want)
	}
}

func TestPullRequestPrefersOpenMatch(t *testing.T) {
	root := t.TempDir()
	ghPath := filepath.Join(root, "gh")
	script := `#!/bin/sh
printf '%s' '[
  {
    "number": 8,
    "state": "MERGED",
    "mergedAt": "2026-07-20T00:00:00Z",
    "url": "https://example.test/pull/8",
    "baseRefName": "main",
    "headRefName": "feature"
  },
  {
    "number": 9,
    "state": "OPEN",
    "mergedAt": null,
    "url": "https://example.test/pull/9",
    "baseRefName": "main",
    "headRefName": "feature"
  }
]'
`
	if err := os.WriteFile(ghPath, []byte(script), 0o755); err != nil {
		t.Fatalf("write fake gh: %v", err)
	}
	t.Setenv("WT_STACK_GH_BIN", ghPath)

	client := NewClient(root, os.Stdout, os.Stderr)
	pullRequest, err := client.PullRequest(
		context.Background(),
		"example/repository",
		"feature",
	)
	if err != nil {
		t.Fatalf("read pull request: %v", err)
	}
	if pullRequest == nil {
		t.Fatal("pull request is nil")
	}
	if pullRequest.Number != 9 || pullRequest.Merged {
		t.Fatalf("unexpected pull request: %#v", pullRequest)
	}
}
