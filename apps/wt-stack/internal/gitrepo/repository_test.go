package gitrepo

import (
	"slices"
	"strings"
	"testing"
)

func TestParseWorktrees(t *testing.T) {
	t.Parallel()

	worktrees := parseWorktrees(strings.TrimSpace(`
worktree /worktrees/zeta
HEAD 2222222
branch refs/heads/feature-zeta

worktree /repositories/example/.git
bare

worktree /worktrees/alpha
HEAD 1111111
detached
`))
	want := []Worktree{
		{Path: "/repositories/example/.git", Bare: true},
		{Path: "/worktrees/alpha", Detached: true},
		{Path: "/worktrees/zeta", Branch: "feature-zeta"},
	}
	if !slices.Equal(worktrees, want) {
		t.Fatalf("worktrees = %#v, want %#v", worktrees, want)
	}
	if empty := parseWorktrees(""); len(empty) != 0 || empty == nil {
		t.Fatalf("empty worktrees = %#v, want non-nil empty slice", empty)
	}
}

func TestPushArguments(t *testing.T) {
	t.Parallel()

	got := pushArguments(
		"origin",
		[]string{"feature-one", "feature-two"},
		map[string]string{"feature-one": "old-one"},
	)
	want := []string{
		"push",
		"origin",
		"--atomic",
		"--force-with-lease=refs/heads/feature-one:old-one",
		"--force-with-lease=refs/heads/feature-two:",
		"refs/heads/feature-one:refs/heads/feature-one",
		"refs/heads/feature-two:refs/heads/feature-two",
	}
	if !slices.Equal(got, want) {
		t.Fatalf("push arguments = %#v, want %#v", got, want)
	}
}

func TestCommandErrorRedactsCredentials(t *testing.T) {
	t.Parallel()

	err := (&CommandError{
		Args: []string{
			"fetch",
			"https://user:argument-token@example.com/repository.git",
		},
		Stderr: "fatal: https://user:stderr-token@example.com/repository.git",
	}).Error()
	if strings.Contains(err, "argument-token") ||
		strings.Contains(err, "stderr-token") {
		t.Fatalf("command error leaked credentials: %s", err)
	}
	if !strings.Contains(err, "https://***@example.com") {
		t.Fatalf("command error did not retain useful host context: %s", err)
	}
}

func TestRemoteRef(t *testing.T) {
	t.Parallel()

	if got := RemoteRef("upstream", "feature"); got !=
		"refs/remotes/upstream/feature" {
		t.Fatalf("remote ref = %q", got)
	}
}
