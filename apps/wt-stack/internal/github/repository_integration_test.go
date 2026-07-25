//go:build integration

package github

import (
	"context"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestRepositoryRejectsUnknownRemoteHost(t *testing.T) {
	root := t.TempDir()
	runGit(t, root, "init", "--initial-branch=main")
	runGit(
		t,
		root,
		"remote",
		"add",
		"origin",
		"https://attacker.example/example/repository.git",
	)
	client := NewClient(root)
	_, err := client.Repository(context.Background(), "origin")
	if err == nil || !strings.Contains(err.Error(), "not configured") {
		t.Fatalf("Repository() error = %v, want unknown-host rejection", err)
	}
}

func TestRepositoryExpandsInsteadOfRemote(t *testing.T) {
	root := t.TempDir()
	runGit(t, root, "init", "--initial-branch=main")
	runGit(
		t,
		root,
		"config",
		`url.git@github.com:.insteadOf`,
		"gh:",
	)
	runGit(t, root, "remote", "add", "origin", "gh:example/repository.git")
	client := NewClient(root)
	repository, err := client.Repository(context.Background(), "origin")
	if err != nil {
		t.Fatalf("resolve rewritten remote: %v", err)
	}
	if repository.Host != "github.com" ||
		repository.Slug() != "example/repository" {
		t.Fatalf("unexpected repository: %#v", repository)
	}
}

func TestGitCommitMessage(t *testing.T) {
	root := t.TempDir()
	runGit(t, root, "init", "--initial-branch=main")
	runGit(t, root, "config", "user.email", "wt-stack@example.test")
	runGit(t, root, "config", "user.name", "wt-stack")
	runGit(t, root, "config", "commit.gpgsign", "false")
	if err := os.WriteFile(
		filepath.Join(root, "file.txt"),
		[]byte("content\n"),
		0o600,
	); err != nil {
		t.Fatalf("write fixture: %v", err)
	}
	runGit(t, root, "add", "file.txt")
	runGit(t, root, "commit", "-m", "Feature two", "-m", "Pull request body")
	runGit(t, root, "branch", "feature-two")

	title, body, err := NewClient(root).gitCommitMessage(
		context.Background(),
		"feature-two",
	)
	if err != nil {
		t.Fatalf("read commit message: %v", err)
	}
	if title != "Feature two" || body != "Pull request body" {
		t.Fatalf("commit message = %q, %q", title, body)
	}
}

func runGit(t *testing.T, dir string, arguments ...string) {
	t.Helper()
	command := exec.Command("git", arguments...)
	command.Dir = dir
	command.Stdout = io.Discard
	command.Stderr = io.Discard
	if err := command.Run(); err != nil {
		t.Fatalf("git %s: %v", strings.Join(arguments, " "), err)
	}
}
