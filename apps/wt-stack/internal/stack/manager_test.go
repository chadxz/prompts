package stack

import (
	"context"
	"errors"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"github.com/chadxz/prompts/apps/wt-stack/internal/gitrepo"
	"github.com/chadxz/prompts/apps/wt-stack/internal/state"
)

func TestManagerRebasesAndPushesAcrossSiblingWorktrees(t *testing.T) {
	t.Parallel()

	fixture := newRepositoryFixture(t)
	context := context.Background()
	repository, err := gitrepo.Discover(context, fixture.bottomWorktree)
	if err != nil {
		t.Fatalf("discover repository: %v", err)
	}
	manager := NewManager(repository, os.Stdout, os.Stderr)

	initialized, err := manager.Init(context, InitOptions{
		Name:     "delivery",
		Remote:   "origin",
		Trunk:    "main",
		Branches: []string{"feature-one", "feature-two"},
	})
	if err != nil {
		t.Fatalf("initialize stack: %v", err)
	}
	if len(initialized.Branches) != 2 {
		t.Fatalf("initialized %d branches, want 2", len(initialized.Branches))
	}

	secondRepository, err := gitrepo.Discover(context, fixture.topWorktree)
	if err != nil {
		t.Fatalf("discover repository from second worktree: %v", err)
	}
	secondManager := NewManager(secondRepository, os.Stdout, os.Stderr)
	statuses, err := secondManager.Status(context, "delivery")
	if err != nil {
		t.Fatalf("read shared status: %v", err)
	}
	if len(statuses) != 1 || len(statuses[0].Branches) != 2 {
		t.Fatalf("unexpected status: %#v", statuses)
	}

	fixture.writeAndCommit(
		fixture.seed,
		"trunk.txt",
		"new trunk\n",
		"advance trunk",
	)
	fixture.git(fixture.seed, "push", "origin", "main")

	if err := manager.Rebase(context, RebaseOptions{
		StackName: "delivery",
		Fetch:     true,
	}); err != nil {
		t.Fatalf("rebase stack: %v", err)
	}

	trunkSHA := fixture.output(fixture.container, "rev-parse", "origin/main")
	bottomSHA := fixture.output(fixture.container, "rev-parse", "feature-one")
	topSHA := fixture.output(fixture.container, "rev-parse", "feature-two")
	fixture.git(fixture.container, "merge-base", "--is-ancestor", trunkSHA, bottomSHA)
	fixture.git(fixture.container, "merge-base", "--is-ancestor", bottomSHA, topSHA)

	if err := manager.Push(context, "delivery"); err != nil {
		t.Fatalf("push stack: %v", err)
	}
	if got := fixture.output(fixture.remote, "rev-parse", "feature-one"); got != bottomSHA {
		t.Fatalf("remote feature-one = %s, want %s", got, bottomSHA)
	}
	if got := fixture.output(fixture.remote, "rev-parse", "feature-two"); got != topSHA {
		t.Fatalf("remote feature-two = %s, want %s", got, topSHA)
	}

	locked, err := state.NewStore(repository.CommonDir).Lock()
	if err != nil {
		t.Fatalf("lock shared state: %v", err)
	}
	defer func() {
		if closeErr := locked.Close(); closeErr != nil {
			t.Errorf("close shared state: %v", closeErr)
		}
	}()
	file, err := locked.Load()
	if err != nil {
		t.Fatalf("load shared state: %v", err)
	}
	stack, exists := file.FindStack("delivery")
	if !exists {
		t.Fatal("delivery stack is missing from shared state")
	}
	if stack.Branches[0].Base != trunkSHA {
		t.Fatalf("bottom base = %s, want %s", stack.Branches[0].Base, trunkSHA)
	}
	if stack.Branches[1].Base != bottomSHA {
		t.Fatalf("top base = %s, want %s", stack.Branches[1].Base, bottomSHA)
	}
}

func TestManagerAbortRestoresAConflictedCascade(t *testing.T) {
	t.Parallel()

	fixture := newRepositoryFixture(t)
	fixture.writeAndCommit(
		fixture.bottomWorktree,
		"base.txt",
		"feature version\n",
		"change base on feature",
	)
	originalSHA := fixture.output(
		fixture.container,
		"rev-parse",
		"feature-one",
	)

	context := context.Background()
	repository, err := gitrepo.Discover(context, fixture.bottomWorktree)
	if err != nil {
		t.Fatalf("discover repository: %v", err)
	}
	manager := NewManager(repository, os.Stdout, os.Stderr)
	if _, err := manager.Init(context, InitOptions{
		Name:     "conflict",
		Remote:   "origin",
		Trunk:    "main",
		Branches: []string{"feature-one"},
	}); err != nil {
		t.Fatalf("initialize stack: %v", err)
	}

	fixture.writeAndCommit(
		fixture.seed,
		"base.txt",
		"trunk version\n",
		"change base on trunk",
	)
	fixture.git(fixture.seed, "push", "origin", "main")

	err = manager.Rebase(context, RebaseOptions{
		StackName: "conflict",
		Fetch:     true,
	})
	var conflict *RebaseConflict
	if !errors.As(err, &conflict) {
		t.Fatalf("rebase error = %v, want RebaseConflict", err)
	}
	expectedWorktree, err := filepath.EvalSymlinks(fixture.bottomWorktree)
	if err != nil {
		t.Fatalf("resolve worktree path: %v", err)
	}
	if conflict.Branch != "feature-one" ||
		conflict.Worktree != expectedWorktree {
		t.Fatalf("unexpected conflict: %#v", conflict)
	}
	if !repository.RebaseInProgress(context, fixture.bottomWorktree) {
		t.Fatal("expected a rebase in progress")
	}

	if err := manager.Abort(context); err != nil {
		t.Fatalf("abort cascade: %v", err)
	}
	if repository.RebaseInProgress(context, fixture.bottomWorktree) {
		t.Fatal("rebase is still in progress")
	}
	if got := fixture.output(
		fixture.container,
		"rev-parse",
		"feature-one",
	); got != originalSHA {
		t.Fatalf("restored SHA = %s, want %s", got, originalSHA)
	}
}

func TestManagerContinuesAConflictedCascade(t *testing.T) {
	t.Parallel()

	fixture := newRepositoryFixture(t)
	fixture.writeAndCommit(
		fixture.bottomWorktree,
		"base.txt",
		"feature version\n",
		"change base on feature",
	)

	context := context.Background()
	repository, err := gitrepo.Discover(context, fixture.bottomWorktree)
	if err != nil {
		t.Fatalf("discover repository: %v", err)
	}
	manager := NewManager(repository, os.Stdout, os.Stderr)
	if _, err := manager.Init(context, InitOptions{
		Name:     "conflict",
		Remote:   "origin",
		Trunk:    "main",
		Branches: []string{"feature-one"},
	}); err != nil {
		t.Fatalf("initialize stack: %v", err)
	}

	fixture.writeAndCommit(
		fixture.seed,
		"base.txt",
		"trunk version\n",
		"change base on trunk",
	)
	fixture.git(fixture.seed, "push", "origin", "main")
	err = manager.Rebase(context, RebaseOptions{
		StackName: "conflict",
		Fetch:     true,
	})
	var conflict *RebaseConflict
	if !errors.As(err, &conflict) {
		t.Fatalf("rebase error = %v, want RebaseConflict", err)
	}

	if err := os.WriteFile(
		filepath.Join(conflict.Worktree, "base.txt"),
		[]byte("resolved version\n"),
		0o644,
	); err != nil {
		t.Fatalf("resolve conflict: %v", err)
	}
	fixture.git(conflict.Worktree, "add", "base.txt")
	if err := manager.Continue(context); err != nil {
		t.Fatalf("continue cascade: %v", err)
	}
	if repository.RebaseInProgress(context, conflict.Worktree) {
		t.Fatal("rebase is still in progress")
	}
	trunkSHA := fixture.output(fixture.container, "rev-parse", "origin/main")
	featureSHA := fixture.output(fixture.container, "rev-parse", "feature-one")
	fixture.git(
		fixture.container,
		"merge-base",
		"--is-ancestor",
		trunkSHA,
		featureSHA,
	)
}

type repositoryFixture struct {
	t              *testing.T
	remote         string
	seed           string
	container      string
	bottomWorktree string
	topWorktree    string
}

func newRepositoryFixture(t *testing.T) *repositoryFixture {
	t.Helper()

	root := t.TempDir()
	fixture := &repositoryFixture{
		t:              t,
		remote:         filepath.Join(root, "remote.git"),
		seed:           filepath.Join(root, "seed"),
		container:      filepath.Join(root, "repository"),
		bottomWorktree: filepath.Join(root, "repository", "feature-one"),
		topWorktree:    filepath.Join(root, "repository", "feature-two"),
	}

	fixture.git(root, "init", "--bare", fixture.remote)
	fixture.git(root, "init", "--initial-branch=main", fixture.seed)
	fixture.git(fixture.seed, "config", "user.name", "Test User")
	fixture.git(fixture.seed, "config", "user.email", "test@example.com")
	fixture.writeAndCommit(fixture.seed, "base.txt", "base\n", "initial commit")
	fixture.git(fixture.seed, "remote", "add", "origin", fixture.remote)
	fixture.git(fixture.seed, "push", "--set-upstream", "origin", "main")
	fixture.git(fixture.remote, "symbolic-ref", "HEAD", "refs/heads/main")

	if err := os.MkdirAll(fixture.container, 0o755); err != nil {
		t.Fatalf("create repository container: %v", err)
	}
	fixture.git(root, "clone", "--bare", fixture.remote,
		filepath.Join(fixture.container, ".git"))
	fixture.git(fixture.container, "config", "remote.origin.fetch",
		"+refs/heads/*:refs/remotes/origin/*")
	fixture.git(fixture.container, "fetch", "origin")
	fixture.git(fixture.container, "worktree", "add",
		filepath.Join(fixture.container, "main"), "main")
	fixture.git(fixture.container, "worktree", "add", "-b", "feature-one",
		fixture.bottomWorktree, "main")
	fixture.git(fixture.bottomWorktree, "config", "user.name", "Test User")
	fixture.git(fixture.bottomWorktree, "config", "user.email", "test@example.com")
	fixture.writeAndCommit(
		fixture.bottomWorktree,
		"feature-one.txt",
		"one\n",
		"add feature one",
	)
	fixture.git(fixture.container, "worktree", "add", "-b", "feature-two",
		fixture.topWorktree, "feature-one")
	fixture.writeAndCommit(
		fixture.topWorktree,
		"feature-two.txt",
		"two\n",
		"add feature two",
	)

	return fixture
}

func (f *repositoryFixture) writeAndCommit(
	worktree string,
	name string,
	content string,
	message string,
) {
	f.t.Helper()
	if err := os.WriteFile(filepath.Join(worktree, name), []byte(content), 0o644); err != nil {
		f.t.Fatalf("write %s: %v", name, err)
	}
	f.git(worktree, "add", name)
	f.git(worktree, "commit", "-m", message)
}

func (f *repositoryFixture) git(dir string, arguments ...string) {
	f.t.Helper()
	command := exec.Command("git", append([]string{"-C", dir}, arguments...)...)
	command.Stdout = io.Discard
	var stderr strings.Builder
	command.Stderr = &stderr
	if err := command.Run(); err != nil {
		f.t.Fatalf("git %s: %v\n%s", strings.Join(arguments, " "), err, stderr.String())
	}
}

func (f *repositoryFixture) output(dir string, arguments ...string) string {
	f.t.Helper()
	command := exec.Command("git", append([]string{"-C", dir}, arguments...)...)
	output, err := command.CombinedOutput()
	if err != nil {
		f.t.Fatalf("git %s: %v\n%s", strings.Join(arguments, " "), err, output)
	}
	return strings.TrimSpace(string(output))
}
