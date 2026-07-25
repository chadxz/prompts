package gitrepo

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

var credentialPattern = regexp.MustCompile(
	`(?i)([a-z][a-z0-9+.-]*://)[^/@\s]+@`,
)

// Worktree describes one entry from git worktree list.
type Worktree struct {
	Path     string `json:"path"`
	Branch   string `json:"branch,omitempty"`
	Bare     bool   `json:"bare"`
	Detached bool   `json:"detached"`
}

// Repository describes a bare repository container and its linked worktrees.
type Repository struct {
	CommonDir string
	Container string
	StartDir  string
	gitBin    string
	out       io.Writer
	err       io.Writer
}

// CommandError preserves stderr and the process exit code for a Git failure.
type CommandError struct {
	Args     []string
	Dir      string
	Stderr   string
	ExitCode int
}

// Error describes the failed Git command.
func (e *CommandError) Error() string {
	command := redactCredentials("git " + strings.Join(e.Args, " "))
	if e.Stderr == "" {
		return fmt.Sprintf("%s failed with exit code %d", command, e.ExitCode)
	}
	return fmt.Sprintf("%s: %s", command, redactCredentials(e.Stderr))
}

// Discover resolves the repository's common Git directory from any worktree or
// from the bare repository container.
func Discover(ctx context.Context, startDir string) (*Repository, error) {
	gitBin := os.Getenv("WT_STACK_GIT_BIN")
	if gitBin == "" {
		gitBin = "git"
	}
	commonDir, err := commandOutput(ctx, gitBin, startDir,
		"rev-parse", "--path-format=absolute", "--git-common-dir")
	if err != nil {
		return nil, fmt.Errorf("discovering common Git directory: %w", err)
	}
	commonDir = filepath.Clean(commonDir)
	return &Repository{
		CommonDir: commonDir,
		Container: filepath.Dir(commonDir),
		StartDir:  startDir,
		gitBin:    gitBin,
		out:       os.Stdout,
		err:       os.Stderr,
	}, nil
}

// SetInteractiveWriters selects where interactive Git output is written.
func (r *Repository) SetInteractiveWriters(out io.Writer, errOut io.Writer) {
	r.out = out
	r.err = errOut
}

// CurrentBranch returns the checked-out branch for the starting worktree.
func (r *Repository) CurrentBranch(ctx context.Context) (string, error) {
	branch, err := r.Output(ctx, r.StartDir, "symbolic-ref", "--short", "HEAD")
	if err != nil {
		return "", fmt.Errorf("determining current branch: %w", err)
	}
	return branch, nil
}

// Worktrees lists all linked worktrees and the bare repository container.
func (r *Repository) Worktrees(ctx context.Context) ([]Worktree, error) {
	output, err := r.Output(ctx, r.Container, "worktree", "list", "--porcelain")
	if err != nil {
		return nil, fmt.Errorf("listing worktrees: %w", err)
	}
	return parseWorktrees(output), nil
}

func parseWorktrees(output string) []Worktree {
	if output == "" {
		return []Worktree{}
	}

	blocks := strings.Split(output, "\n\n")
	worktrees := make([]Worktree, 0, len(blocks))
	for _, block := range blocks {
		var worktree Worktree
		for _, line := range strings.Split(block, "\n") {
			key, value, _ := strings.Cut(line, " ")
			switch key {
			case "worktree":
				worktree.Path = value
			case "branch":
				worktree.Branch = strings.TrimPrefix(value, "refs/heads/")
			case "bare":
				worktree.Bare = true
			case "detached":
				worktree.Detached = true
			}
		}
		if worktree.Path != "" {
			worktrees = append(worktrees, worktree)
		}
	}
	sort.Slice(worktrees, func(i, j int) bool {
		return worktrees[i].Path < worktrees[j].Path
	})
	return worktrees
}

// WorktreeForBranch returns the worktree that owns a local branch.
func (r *Repository) WorktreeForBranch(
	ctx context.Context,
	branch string,
) (Worktree, bool, error) {
	worktrees, err := r.Worktrees(ctx)
	if err != nil {
		return Worktree{}, false, err
	}
	for _, worktree := range worktrees {
		if worktree.Branch == branch {
			return worktree, true, nil
		}
	}
	return Worktree{}, false, nil
}

// Head resolves a local branch or other revision to its full SHA.
func (r *Repository) Head(ctx context.Context, revision string) (string, error) {
	sha, err := r.Output(ctx, r.Container, "rev-parse", "--verify", revision)
	if err != nil {
		return "", fmt.Errorf("resolving %s: %w", revision, err)
	}
	return sha, nil
}

// MergeBase returns the best common ancestor of two revisions.
func (r *Repository) MergeBase(
	ctx context.Context,
	left string,
	right string,
) (string, error) {
	sha, err := r.Output(ctx, r.Container, "merge-base", left, right)
	if err != nil {
		return "", fmt.Errorf("finding merge base for %s and %s: %w", left, right, err)
	}
	return sha, nil
}

// IsAncestor reports whether ancestor is reachable from descendant.
func (r *Repository) IsAncestor(
	ctx context.Context,
	ancestor string,
	descendant string,
) (bool, error) {
	err := r.Run(ctx, r.Container, "merge-base", "--is-ancestor", ancestor, descendant)
	if err == nil {
		return true, nil
	}
	var commandErr *CommandError
	if errors.As(err, &commandErr) && commandErr.ExitCode == 1 {
		return false, nil
	}
	return false, fmt.Errorf(
		"checking whether %s is an ancestor of %s: %w",
		ancestor,
		descendant,
		err,
	)
}

// IsClean reports whether a worktree has staged, unstaged, or untracked work.
func (r *Repository) IsClean(ctx context.Context, path string) (bool, error) {
	output, err := r.Output(ctx, path, "status", "--porcelain=v1", "--untracked-files=all")
	if err != nil {
		return false, fmt.Errorf("checking worktree %s: %w", path, err)
	}
	return output == "", nil
}

// CreateWorktree creates a branch and checks it out in a new worktree.
func (r *Repository) CreateWorktree(
	ctx context.Context,
	branch string,
	path string,
	base string,
) error {
	if err := r.Run(ctx, r.Container, "worktree", "add", "-b", branch, path, base); err != nil {
		return fmt.Errorf("creating worktree for %s: %w", branch, err)
	}
	return nil
}

// Fetch refreshes the selected remote and prunes deleted remote branches.
func (r *Repository) Fetch(ctx context.Context, remote string) error {
	if err := r.Run(ctx, r.Container, "fetch", "--prune", remote); err != nil {
		return fmt.Errorf("fetching %s: %w", remote, err)
	}
	return nil
}

// ConfigureRerere enables reuse and automatic staging of conflict resolutions.
func (r *Repository) ConfigureRerere(ctx context.Context) error {
	for key, value := range map[string]string{
		"rerere.enabled":    "true",
		"rerere.autoupdate": "true",
	} {
		if err := r.Run(ctx, r.Container, "config", key, value); err != nil {
			return fmt.Errorf("setting %s: %w", key, err)
		}
	}
	return nil
}

// RebaseOnto rebases the branch checked out at path from oldBase onto newBase.
func (r *Repository) RebaseOnto(
	ctx context.Context,
	path string,
	newBase string,
	oldBase string,
) error {
	if err := r.RunInteractive(ctx, path, nil,
		"rebase", "--onto", newBase, oldBase); err != nil {
		return fmt.Errorf("rebasing %s onto %s: %w", path, newBase, err)
	}
	return nil
}

// ContinueRebase continues the rebase in a worktree without opening an editor.
func (r *Repository) ContinueRebase(ctx context.Context, path string) error {
	environment := append(os.Environ(), "GIT_EDITOR=true")
	if err := r.RunInteractive(ctx, path, environment, "rebase", "--continue"); err != nil {
		return fmt.Errorf("continuing rebase in %s: %w", path, err)
	}
	return nil
}

// AbortRebase aborts the rebase in a worktree.
func (r *Repository) AbortRebase(ctx context.Context, path string) error {
	if err := r.RunInteractive(ctx, path, nil, "rebase", "--abort"); err != nil {
		return fmt.Errorf("aborting rebase in %s: %w", path, err)
	}
	return nil
}

// RebaseInProgress reports whether a worktree has an active rebase.
func (r *Repository) RebaseInProgress(ctx context.Context, path string) bool {
	gitDir, err := r.Output(ctx, path,
		"rev-parse", "--path-format=absolute", "--git-dir")
	if err != nil {
		return false
	}
	for _, marker := range []string{"rebase-merge", "rebase-apply"} {
		if info, statErr := os.Stat(filepath.Join(gitDir, marker)); statErr == nil && info.IsDir() {
			return true
		}
	}
	return false
}

// ResetHard restores the current worktree branch to a known commit.
func (r *Repository) ResetHard(ctx context.Context, path string, sha string) error {
	if err := r.RunInteractive(ctx, path, nil, "reset", "--hard", sha); err != nil {
		return fmt.Errorf("restoring %s to %s: %w", path, sha, err)
	}
	return nil
}

// ResetBranch restores a branch without requiring an owning worktree.
func (r *Repository) ResetBranch(
	ctx context.Context,
	branch string,
	sha string,
) error {
	ref := "refs/heads/" + branch
	if err := r.Run(ctx, r.Container, "update-ref", ref, sha); err != nil {
		return fmt.Errorf("restoring %s to %s: %w", ref, sha, err)
	}
	return nil
}

// PushStack pushes branch refs atomically with explicit force-with-lease values.
func (r *Repository) PushStack(
	ctx context.Context,
	remote string,
	branches []string,
) error {
	remoteSHAs := make(map[string]string, len(branches))
	for _, branch := range branches {
		remoteRef := fmt.Sprintf("refs/remotes/%s/%s", remote, branch)
		remoteSHA, err := r.Output(ctx, r.Container,
			"rev-parse", "--verify", "--quiet", remoteRef)
		if err != nil {
			var commandErr *CommandError
			if !errors.As(err, &commandErr) || commandErr.ExitCode != 1 {
				return fmt.Errorf("resolving %s: %w", remoteRef, err)
			}
			remoteSHA = ""
		}
		remoteSHAs[branch] = remoteSHA
	}
	args := pushArguments(remote, branches, remoteSHAs)
	if err := r.RunInteractive(ctx, r.Container, nil, args...); err != nil {
		return fmt.Errorf("pushing stack to %s: %w", remote, err)
	}
	return nil
}

func pushArguments(
	remote string,
	branches []string,
	remoteSHAs map[string]string,
) []string {
	args := []string{"push", remote, "--atomic"}
	for _, branch := range branches {
		args = append(args, fmt.Sprintf(
			"--force-with-lease=refs/heads/%s:%s",
			branch,
			remoteSHAs[branch],
		))
	}
	for _, branch := range branches {
		args = append(args, fmt.Sprintf(
			"refs/heads/%s:refs/heads/%s",
			branch,
			branch,
		))
	}
	return args
}

// RemoteRef returns the fully qualified remote-tracking ref for a branch.
func RemoteRef(remote string, branch string) string {
	return fmt.Sprintf("refs/remotes/%s/%s", remote, branch)
}

// Run executes a Git command and captures its output.
func (r *Repository) Run(ctx context.Context, dir string, args ...string) error {
	_, err := r.run(ctx, dir, nil, false, args...)
	return err
}

// Output executes a Git command and returns trimmed stdout.
func (r *Repository) Output(
	ctx context.Context,
	dir string,
	args ...string,
) (string, error) {
	return r.run(ctx, dir, nil, false, args...)
}

// RunInteractive executes a Git command attached to the current terminal.
func (r *Repository) RunInteractive(
	ctx context.Context,
	dir string,
	environment []string,
	args ...string,
) error {
	_, err := r.run(ctx, dir, environment, true, args...)
	return err
}

func (r *Repository) run(
	ctx context.Context,
	dir string,
	environment []string,
	interactive bool,
	args ...string,
) (string, error) {
	// The configured Git binary is executed directly without a shell.
	command := exec.CommandContext( //nolint:gosec // Git runs without a shell.
		ctx,
		r.gitBin,
		append([]string{"-C", dir}, args...)...,
	)
	if environment != nil {
		command.Env = environment
	}

	var stdout bytes.Buffer
	var stderr bytes.Buffer
	if interactive {
		command.Stdin = os.Stdin
		command.Stdout = r.out
		command.Stderr = io.MultiWriter(r.err, &stderr)
	} else {
		command.Stdout = &stdout
		command.Stderr = &stderr
	}
	if err := command.Run(); err != nil {
		exitCode := 1
		var exitErr *exec.ExitError
		if errors.As(err, &exitErr) {
			exitCode = exitErr.ExitCode()
		}
		return "", &CommandError{
			Args:     args,
			Dir:      dir,
			Stderr:   strings.TrimSpace(stderr.String()),
			ExitCode: exitCode,
		}
	}
	return strings.TrimSpace(stdout.String()), nil
}

func commandOutput(
	ctx context.Context,
	gitBin string,
	dir string,
	args ...string,
) (string, error) {
	// The configured Git binary is executed directly without a shell.
	command := exec.CommandContext( //nolint:gosec // Git runs without a shell.
		ctx,
		gitBin,
		append([]string{"-C", dir}, args...)...,
	)
	output, err := command.CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("%s: %w", strings.TrimSpace(string(output)), err)
	}
	return strings.TrimSpace(string(output)), nil
}

func redactCredentials(value string) string {
	return credentialPattern.ReplaceAllString(value, `${1}***@`)
}
