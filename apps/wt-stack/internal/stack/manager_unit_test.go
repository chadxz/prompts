package stack

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"path/filepath"
	"slices"
	"strings"
	"testing"

	"github.com/chadxz/prompts/apps/wt-stack/internal/github"
	"github.com/chadxz/prompts/apps/wt-stack/internal/gitrepo"
	"github.com/chadxz/prompts/apps/wt-stack/internal/state"
)

func TestManagerInitializesAndAddsBranches(t *testing.T) {
	t.Parallel()

	manager, repository, _, store := newUnitManager(t, &state.File{})
	stack, err := manager.Init(context.Background(), InitOptions{
		Name:     "delivery",
		Remote:   "origin",
		Trunk:    "main",
		Branches: []string{"feature-one"},
	})
	if err != nil {
		t.Fatalf("initialize stack: %v", err)
	}
	if stack.Name != "delivery" || store.saves != 1 {
		t.Fatalf("unexpected initialized stack: %#v, saves=%d", stack, store.saves)
	}
	if !slices.Contains(repository.calls, "fetch:origin") ||
		!slices.Contains(repository.calls, "configure-rerere") {
		t.Fatalf("initialization calls = %v", repository.calls)
	}

	branch, err := manager.Add(context.Background(), AddOptions{
		StackName: "delivery",
		Branch:    "feature-two",
	})
	if err != nil {
		t.Fatalf("add branch: %v", err)
	}
	if branch.Name != "feature-two" || store.saves != 2 {
		t.Fatalf("unexpected added branch: %#v, saves=%d", branch, store.saves)
	}
	if !slices.Contains(repository.calls, "create-worktree:feature-two") {
		t.Fatalf("add calls = %v", repository.calls)
	}
}

func TestManagerRunsStackLifecycleWithFakes(t *testing.T) {
	t.Parallel()

	file := unitStateFile()
	manager, repository, githubClient, store := newUnitManager(t, file)
	ctx := context.Background()

	statuses, err := manager.Status(ctx, "delivery")
	if err != nil {
		t.Fatalf("read status: %v", err)
	}
	if len(statuses) != 1 || !statuses[0].Branches[0].Clean {
		t.Fatalf("unexpected status: %#v", statuses)
	}

	if err := manager.Rebase(ctx, RebaseOptions{
		StackName: "delivery",
		Fetch:     true,
	}); err != nil {
		t.Fatalf("rebase stack: %v", err)
	}
	if !slices.Contains(repository.calls, "rebase:/worktrees/feature-one") {
		t.Fatalf("rebase calls = %v", repository.calls)
	}

	if err := manager.Submit(ctx, SubmitOptions{
		StackName: "delivery",
		Draft:     true,
	}); err != nil {
		t.Fatalf("submit stack: %v", err)
	}
	if githubClient.links != 1 || !githubClient.linkDraft {
		t.Fatalf(
			"GitHub links = %d, draft = %t, want one draft link",
			githubClient.links,
			githubClient.linkDraft,
		)
	}
	if store.file.Stacks[0].Branches[0].PullRequest == nil {
		t.Fatal("submit did not refresh pull request state")
	}

	checks, err := manager.Doctor(ctx, "delivery")
	if err != nil {
		t.Fatalf("run doctor: %v", err)
	}
	if checks["githubRepository"] != "example/repository" ||
		githubClient.authentications != 1 ||
		githubClient.previewChecks != 1 {
		t.Fatalf("unexpected doctor result: %#v", checks)
	}
}

func TestManagerUnstacksLocallyAndRemotely(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name          string
		localOnly     bool
		dissolved     bool
		wantStacks    int
		wantUnstacks  int
		wantDissolved bool
	}{
		{
			name:          "remote stack dissolved",
			dissolved:     true,
			wantStacks:    0,
			wantUnstacks:  1,
			wantDissolved: true,
		},
		{
			name:          "remote stack partially retained",
			dissolved:     false,
			wantStacks:    1,
			wantUnstacks:  1,
			wantDissolved: false,
		},
		{
			name:          "local tracking only",
			localOnly:     true,
			dissolved:     true,
			wantStacks:    0,
			wantUnstacks:  0,
			wantDissolved: true,
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()

			manager, _, githubClient, store := newUnitManager(
				t,
				unitStateFile(),
			)
			githubClient.dissolved = test.dissolved

			dissolved, err := manager.Unstack(
				context.Background(),
				"delivery",
				test.localOnly,
			)
			if err != nil {
				t.Fatalf("unstack: %v", err)
			}
			if dissolved != test.wantDissolved {
				t.Fatalf(
					"dissolved = %t, want %t",
					dissolved,
					test.wantDissolved,
				)
			}
			if len(store.file.Stacks) != test.wantStacks {
				t.Fatalf(
					"stacks = %d, want %d",
					len(store.file.Stacks),
					test.wantStacks,
				)
			}
			if githubClient.unstacks != test.wantUnstacks {
				t.Fatalf(
					"GitHub unstack calls = %d, want %d",
					githubClient.unstacks,
					test.wantUnstacks,
				)
			}
		})
	}
}

func TestManagerContinuesAndAbortsStoredRebases(t *testing.T) {
	t.Parallel()

	t.Run("continue", func(t *testing.T) {
		t.Parallel()

		file := unitStateFile()
		file.Rebase = unitRebaseSession(file.Stacks[0])
		manager, repository, _, store := newUnitManager(t, file)
		repository.rebaseInProgress = true

		if err := manager.Continue(context.Background()); err != nil {
			t.Fatalf("continue rebase: %v", err)
		}
		if !slices.Contains(repository.calls, "continue:/worktrees/feature-one") {
			t.Fatalf("continue calls = %v", repository.calls)
		}
		if store.file.Rebase != nil {
			t.Fatal("continued rebase session was not cleared")
		}
	})

	t.Run("abort", func(t *testing.T) {
		t.Parallel()

		file := unitStateFile()
		file.Rebase = unitRebaseSession(file.Stacks[0])
		manager, repository, _, store := newUnitManager(t, file)
		repository.rebaseInProgress = true

		if err := manager.Abort(context.Background()); err != nil {
			t.Fatalf("abort rebase: %v", err)
		}
		if !slices.Contains(repository.calls, "abort:/worktrees/feature-one") ||
			!slices.Contains(repository.calls, "reset:/worktrees/feature-one:head-one") {
			t.Fatalf("abort calls = %v", repository.calls)
		}
		if store.file.Rebase != nil {
			t.Fatal("aborted rebase session was not cleared")
		}
	})
}

func TestManagerDryRunDoesNotMutateRepositoryOrState(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name    string
		file    func() *state.File
		prepare func(*state.File)
		run     func(*Manager) error
	}{
		{
			name: "init",
			file: func() *state.File {
				return &state.File{}
			},
			run: func(manager *Manager) error {
				_, err := manager.Init(context.Background(), InitOptions{
					Name:     "delivery",
					Remote:   "origin",
					Trunk:    "main",
					Branches: []string{"feature-one"},
				})
				return err
			},
		},
		{
			name: "add",
			run: func(manager *Manager) error {
				_, err := manager.Add(context.Background(), AddOptions{
					StackName: "delivery",
					Branch:    "feature-two",
				})
				return err
			},
		},
		{
			name: "rebase",
			run: func(manager *Manager) error {
				return manager.Rebase(context.Background(), RebaseOptions{
					StackName: "delivery",
					Fetch:     true,
				})
			},
		},
		{
			name: "push",
			run: func(manager *Manager) error {
				return manager.Push(context.Background(), "delivery")
			},
		},
		{
			name: "submit",
			run: func(manager *Manager) error {
				return manager.Submit(context.Background(), SubmitOptions{
					StackName: "delivery",
				})
			},
		},
		{
			name: "refresh",
			run: func(manager *Manager) error {
				return manager.Refresh(context.Background(), "delivery")
			},
		},
		{
			name: "unstack",
			run: func(manager *Manager) error {
				_, err := manager.Unstack(
					context.Background(),
					"delivery",
					false,
				)
				return err
			},
		},
		{
			name: "continue",
			prepare: func(file *state.File) {
				file.Rebase = unitRebaseSession(file.Stacks[0])
			},
			run: func(manager *Manager) error {
				return manager.Continue(context.Background())
			},
		},
		{
			name: "abort",
			prepare: func(file *state.File) {
				file.Rebase = unitRebaseSession(file.Stacks[0])
			},
			run: func(manager *Manager) error {
				return manager.Abort(context.Background())
			},
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()

			file := unitStateFile()
			if test.file != nil {
				file = test.file()
			}
			if test.prepare != nil {
				test.prepare(file)
			}
			manager, repository, githubClient, store := newUnitManager(t, file)
			manager.SetDryRun(true)
			if err := test.run(manager); err != nil {
				t.Fatalf("%s dry run: %v", test.name, err)
			}
			if store.saves != 0 {
				t.Fatalf("state saves = %d, want 0", store.saves)
			}
			if len(repository.calls) != 0 {
				t.Fatalf("dry run mutated repository: %v", repository.calls)
			}
			if githubClient.links != 0 {
				t.Fatalf("GitHub links = %d, want 0", githubClient.links)
			}
			if githubClient.unstacks != 0 {
				t.Fatalf(
					"GitHub unstack calls = %d, want 0",
					githubClient.unstacks,
				)
			}
		})
	}
}

func TestManagerAbortRestoresBranchesWithoutWorktrees(t *testing.T) {
	t.Parallel()

	file := unitStateFile()
	file.Rebase = unitRebaseSession(file.Stacks[0])
	manager, repository, _, store := newUnitManager(t, file)
	delete(repository.worktrees, "feature-one")

	if err := manager.Abort(context.Background()); err != nil {
		t.Fatalf("abort rebase: %v", err)
	}
	if !slices.Contains(
		repository.calls,
		"reset-branch:feature-one:head-one",
	) {
		t.Fatalf("abort calls = %v", repository.calls)
	}
	if store.file.Rebase != nil {
		t.Fatal("aborted rebase session was not cleared")
	}
}

func TestManagerRebaseRecordsOnlyActiveBranchesForRecovery(t *testing.T) {
	t.Parallel()

	file := unitStateFile()
	file.Stacks[0].Branches = append(
		[]state.Branch{{
			Name: "merged",
			Base: "old-base",
			Head: "merged-head",
			PullRequest: &state.PullRequest{
				Number: 1,
				Merged: true,
			},
		}},
		file.Stacks[0].Branches...,
	)
	manager, repository, _, store := newUnitManager(t, file)
	repository.rebaseErr = errors.New("conflict")

	err := manager.Rebase(context.Background(), RebaseOptions{
		StackName: "delivery",
	})
	var conflict *RebaseConflictError
	if !errors.As(err, &conflict) {
		t.Fatalf("rebase error = %v, want conflict", err)
	}
	original := store.file.Rebase.OriginalBranches
	if _, exists := original["merged"]; exists {
		t.Fatalf("recovery includes merged branch: %#v", original)
	}
	if original["feature-one"] != "head-one" {
		t.Fatalf("recovery branches = %#v", original)
	}
}

func TestManagerRejectsInvalidRebaseState(t *testing.T) {
	t.Parallel()

	for _, operation := range []string{"continue", "abort"} {
		t.Run(operation, func(t *testing.T) {
			t.Parallel()

			file := unitStateFile()
			file.Rebase = unitRebaseSession(file.Stacks[0])
			file.Rebase.CurrentIndex = len(file.Stacks[0].Branches)
			manager, _, _, _ := newUnitManager(t, file)

			var err error
			if operation == "continue" {
				err = manager.Continue(context.Background())
			} else {
				err = manager.Abort(context.Background())
			}
			if err == nil || !strings.Contains(err.Error(), "invalid") {
				t.Fatalf("%s error = %v", operation, err)
			}
		})
	}
}

func TestManagerRemoteMutationsRejectPausedRebase(t *testing.T) {
	t.Parallel()

	for _, operation := range []string{"refresh", "unstack"} {
		t.Run(operation, func(t *testing.T) {
			t.Parallel()

			file := unitStateFile()
			file.Rebase = unitRebaseSession(file.Stacks[0])
			manager, _, githubClient, store := newUnitManager(t, file)

			var err error
			if operation == "refresh" {
				err = manager.Refresh(context.Background(), "delivery")
			} else {
				_, err = manager.Unstack(
					context.Background(),
					"delivery",
					false,
				)
			}
			if err == nil ||
				!strings.Contains(err.Error(), "continued or aborted") {
				t.Fatalf("%s error = %v", operation, err)
			}
			if store.saves != 0 || githubClient.unstacks != 0 {
				t.Fatalf(
					"state saves = %d, unstack calls = %d",
					store.saves,
					githubClient.unstacks,
				)
			}
		})
	}
}

func TestManagerReportsSelectionAndConflictErrors(t *testing.T) {
	t.Parallel()

	manager, repository, _, _ := newUnitManager(t, &state.File{
		Stacks: []state.Stack{
			{Name: "one"},
			{Name: "two"},
		},
	})
	repository.currentBranch = "untracked"
	if _, err := manager.Status(context.Background(), "missing"); err == nil {
		t.Fatal("status accepted a missing stack")
	}
	if err := manager.Push(context.Background(), ""); err == nil ||
		err.Error() != "select a stack with --stack" {
		t.Fatalf("push error = %v", err)
	}

	conflict := &RebaseConflictError{
		StackName: "delivery",
		Branch:    "feature-one",
		Worktree:  "/worktrees/feature-one",
	}
	if got := conflict.Error(); got !=
		"rebase paused for feature-one in /worktrees/feature-one" {
		t.Fatalf("conflict error = %q", got)
	}
}

func TestNewManagerWiresFileStateStore(t *testing.T) {
	t.Parallel()

	commonDir := t.TempDir()
	manager := NewManager(&gitrepo.Repository{
		CommonDir: commonDir,
		Container: filepath.Dir(commonDir),
		StartDir:  commonDir,
	}, io.Discard, io.Discard)
	manager.SetDryRun(true)

	locked, err := manager.store.Lock()
	if err != nil {
		t.Fatalf("lock file state store: %v", err)
	}
	if err := locked.Close(); err != nil {
		t.Fatalf("close file state store: %v", err)
	}
	if manager.commonDir != commonDir || !manager.dryRun {
		t.Fatalf("unexpected manager: %#v", manager)
	}
}

func unitStateFile() *state.File {
	return &state.File{
		Version: 1,
		Stacks: []state.Stack{{
			Name:   "delivery",
			Remote: "origin",
			Trunk:  "main",
			Branches: []state.Branch{{
				Name: "feature-one",
				Base: "base-one",
				Head: "head-one",
			}},
		}},
	}
}

func unitRebaseSession(stack state.Stack) *state.RebaseSession {
	return &state.RebaseSession{
		StackName:        stack.Name,
		CurrentIndex:     0,
		CurrentWorktree:  "/worktrees/feature-one",
		OriginalBranches: map[string]string{"feature-one": "head-one"},
		OriginalStack:    state.CloneStack(stack),
	}
}

type fakeRepository struct {
	currentBranch    string
	worktrees        map[string]gitrepo.Worktree
	heads            map[string]string
	clean            map[string]bool
	rebaseInProgress bool
	rebaseErr        error
	calls            []string
}

func (r *fakeRepository) CurrentBranch(context.Context) (string, error) {
	if r.currentBranch == "" {
		return "", errors.New("detached HEAD")
	}
	return r.currentBranch, nil
}

func (r *fakeRepository) WorktreeForBranch(
	_ context.Context,
	branch string,
) (gitrepo.Worktree, bool, error) {
	worktree, exists := r.worktrees[branch]
	return worktree, exists, nil
}

func (r *fakeRepository) Head(_ context.Context, revision string) (string, error) {
	head, exists := r.heads[revision]
	if !exists {
		return "", errors.New("revision not found")
	}
	return head, nil
}

func (r *fakeRepository) IsAncestor(
	context.Context,
	string,
	string,
) (bool, error) {
	return true, nil
}

func (r *fakeRepository) IsClean(
	_ context.Context,
	path string,
) (bool, error) {
	return r.clean[path], nil
}

func (r *fakeRepository) CreateWorktree(
	_ context.Context,
	branch string,
	path string,
	_ string,
) error {
	r.calls = append(r.calls, "create-worktree:"+branch)
	r.worktrees[branch] = gitrepo.Worktree{Path: path, Branch: branch}
	return nil
}

func (r *fakeRepository) Fetch(_ context.Context, remote string) error {
	r.calls = append(r.calls, "fetch:"+remote)
	return nil
}

func (r *fakeRepository) ConfigureRerere(context.Context) error {
	r.calls = append(r.calls, "configure-rerere")
	return nil
}

func (r *fakeRepository) RebaseOnto(
	_ context.Context,
	path string,
	_ string,
	_ string,
) error {
	r.calls = append(r.calls, "rebase:"+path)
	if r.rebaseErr != nil {
		return r.rebaseErr
	}
	r.heads["refs/heads/feature-one"] = "rebased-head"
	return nil
}

func (r *fakeRepository) ContinueRebase(
	_ context.Context,
	path string,
) error {
	r.calls = append(r.calls, "continue:"+path)
	r.rebaseInProgress = false
	r.heads["refs/heads/feature-one"] = "continued-head"
	return nil
}

func (r *fakeRepository) AbortRebase(
	_ context.Context,
	path string,
) error {
	r.calls = append(r.calls, "abort:"+path)
	r.rebaseInProgress = false
	return nil
}

func (r *fakeRepository) RebaseInProgress(
	context.Context,
	string,
) bool {
	return r.rebaseInProgress
}

func (r *fakeRepository) ResetHard(
	_ context.Context,
	path string,
	sha string,
) error {
	r.calls = append(r.calls, "reset:"+path+":"+sha)
	return nil
}

func (r *fakeRepository) ResetBranch(
	_ context.Context,
	branch string,
	sha string,
) error {
	r.calls = append(r.calls, "reset-branch:"+branch+":"+sha)
	return nil
}

func (r *fakeRepository) PushStack(
	_ context.Context,
	remote string,
	_ []string,
) error {
	r.calls = append(r.calls, "push:"+remote)
	return nil
}

type fakeGitHubClient struct {
	pullRequests    map[string]*state.PullRequest
	links           int
	linkDraft       bool
	unstacks        int
	dissolved       bool
	authentications int
	previewChecks   int
}

func (c *fakeGitHubClient) Repository(
	context.Context,
	string,
) (github.Repository, error) {
	return github.Repository{
		Host:   "github.com",
		Owner:  "example",
		Name:   "repository",
		APIURL: "https://api.github.com",
	}, nil
}

func (c *fakeGitHubClient) Authenticate(context.Context, string) error {
	c.authentications++
	return nil
}

func (c *fakeGitHubClient) StacksAvailable(
	context.Context,
	github.Repository,
) error {
	c.previewChecks++
	return nil
}

func (c *fakeGitHubClient) PullRequest(
	_ context.Context,
	_ github.Repository,
	branch string,
) (*state.PullRequest, error) {
	return c.pullRequests[branch], nil
}

func (c *fakeGitHubClient) Link(
	_ context.Context,
	_ github.Repository,
	_ string,
	_ []string,
	draft bool,
) error {
	c.links++
	c.linkDraft = draft
	return nil
}

func (c *fakeGitHubClient) Unstack(
	_ context.Context,
	_ github.Repository,
	pullRequestNumbers []int,
) (bool, error) {
	c.unstacks++
	if !slices.Equal(pullRequestNumbers, []int{42}) {
		return false, errors.New("unexpected pull request numbers")
	}
	return c.dissolved, nil
}

type memoryStore struct {
	file  *state.File
	saves int
}

func (s *memoryStore) Lock() (lockedState, error) {
	return &memoryLock{store: s}, nil
}

type memoryLock struct {
	store *memoryStore
}

func (l *memoryLock) Load() (*state.File, error) {
	return cloneStateFile(l.store.file), nil
}

func (l *memoryLock) Save(file *state.File) error {
	l.store.file = cloneStateFile(file)
	l.store.saves++
	return nil
}

func (l *memoryLock) Close() error {
	return nil
}

func cloneStateFile(file *state.File) *state.File {
	data, err := json.Marshal(file)
	if err != nil {
		panic(err)
	}
	var clone state.File
	if err := json.Unmarshal(data, &clone); err != nil {
		panic(err)
	}
	return &clone
}

func newUnitManager(
	t *testing.T,
	file *state.File,
) (*Manager, *fakeRepository, *fakeGitHubClient, *memoryStore) {
	t.Helper()

	container := t.TempDir()
	repository := &fakeRepository{
		currentBranch: "feature-one",
		worktrees: map[string]gitrepo.Worktree{
			"feature-one": {
				Path:   "/worktrees/feature-one",
				Branch: "feature-one",
			},
		},
		heads: map[string]string{
			"refs/remotes/origin/main": "trunk-head",
			"refs/heads/feature-one":   "head-one",
		},
		clean: map[string]bool{"/worktrees/feature-one": true},
	}
	githubClient := &fakeGitHubClient{
		pullRequests: map[string]*state.PullRequest{
			"feature-one": {
				Number: 42,
				URL:    "https://github.com/example/repository/pull/42",
				Base:   "main",
				State:  "open",
			},
		},
	}
	store := &memoryStore{file: cloneStateFile(file)}
	manager := &Manager{
		repository: repository,
		github:     githubClient,
		store:      store,
		commonDir:  filepath.Join(container, ".git"),
		container:  container,
	}
	return manager, repository, githubClient, store
}
