// Package stack coordinates worktree-safe stacked branch operations.
package stack

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/chadxz/prompts/apps/wt-stack/internal/github"
	"github.com/chadxz/prompts/apps/wt-stack/internal/gitrepo"
	"github.com/chadxz/prompts/apps/wt-stack/internal/state"
)

var unsafePathCharacters = regexp.MustCompile(`[^A-Za-z0-9._-]+`)

// Manager coordinates Git, local state, and GitHub operations.
type Manager struct {
	Repository *gitrepo.Repository
	GitHub     *github.Client
	Store      *state.Store
	DryRun     bool
}

// InitOptions configures stack adoption.
type InitOptions struct {
	Name     string
	Remote   string
	Trunk    string
	Branches []string
}

// AddOptions configures a new branch worktree.
type AddOptions struct {
	StackName string
	Branch    string
	Path      string
}

// RebaseOptions configures a cascading rebase.
type RebaseOptions struct {
	StackName string
	Fetch     bool
}

// StackStatus is a live view of one locally tracked stack.
type StackStatus struct {
	Name     string         `json:"name"`
	Remote   string         `json:"remote"`
	Trunk    string         `json:"trunk"`
	Branches []BranchStatus `json:"branches"`
}

// BranchStatus combines persisted metadata with current worktree state.
type BranchStatus struct {
	Name        string             `json:"name"`
	Worktree    string             `json:"worktree,omitempty"`
	Clean       bool               `json:"clean"`
	Head        string             `json:"head"`
	Base        string             `json:"base"`
	Drifted     bool               `json:"drifted"`
	PullRequest *state.PullRequest `json:"pullRequest,omitempty"`
}

// RebaseConflict reports the worktree that needs agent attention.
type RebaseConflict struct {
	StackName string
	Branch    string
	Worktree  string
}

// Error describes a paused cascading rebase.
func (e *RebaseConflict) Error() string {
	return fmt.Sprintf("rebase paused for %s in %s", e.Branch, e.Worktree)
}

// NewManager creates a manager for a discovered repository.
func NewManager(
	repository *gitrepo.Repository,
	out io.Writer,
	errOut io.Writer,
) *Manager {
	repository.SetInteractiveWriters(out, errOut)
	return &Manager{
		Repository: repository,
		GitHub:     github.NewClient(repository.StartDir),
		Store:      state.NewStore(repository.CommonDir),
	}
}

// Init adopts an existing linear branch chain into repository-wide state.
func (m *Manager) Init(ctx context.Context, options InitOptions) (*state.Stack, error) {
	if len(options.Branches) == 0 {
		currentBranch, err := m.Repository.CurrentBranch(ctx)
		if err != nil {
			return nil, errors.New("specify at least one branch from the bare repository container")
		}
		options.Branches = []string{currentBranch}
	}
	if options.Remote == "" {
		options.Remote = "origin"
	}
	if options.Trunk == "" {
		options.Trunk = "main"
	}
	if options.Name == "" {
		options.Name = options.Branches[0]
	}

	locked, err := m.Store.Lock()
	if err != nil {
		return nil, err
	}
	defer func() {
		_ = locked.Close()
	}()

	file, err := locked.Load()
	if err != nil {
		return nil, err
	}
	if file.Rebase != nil {
		return nil, fmt.Errorf("rebase for stack %s must be continued or aborted", file.Rebase.StackName)
	}
	if _, exists := file.FindStack(options.Name); exists {
		return nil, fmt.Errorf("stack %q already exists", options.Name)
	}
	for _, branch := range options.Branches {
		if stack, exists := file.FindStackForBranch(branch); exists {
			return nil, fmt.Errorf("branch %q already belongs to stack %q", branch, stack.Name)
		}
	}

	if err := m.Repository.Fetch(ctx, options.Remote); err != nil {
		return nil, err
	}
	parentRef := gitrepo.RemoteRef(options.Remote, options.Trunk)
	branches := make([]state.Branch, 0, len(options.Branches))
	for _, branchName := range options.Branches {
		if _, exists, worktreeErr := m.Repository.WorktreeForBranch(ctx, branchName); worktreeErr != nil {
			return nil, worktreeErr
		} else if !exists {
			return nil, fmt.Errorf("branch %q is not checked out in a worktree", branchName)
		}

		parentSHA, err := m.Repository.Head(ctx, parentRef)
		if err != nil {
			return nil, err
		}
		headSHA, err := m.Repository.Head(ctx, "refs/heads/"+branchName)
		if err != nil {
			return nil, err
		}
		ancestor, err := m.Repository.IsAncestor(ctx, parentSHA, headSHA)
		if err != nil {
			return nil, err
		}
		if !ancestor {
			return nil, fmt.Errorf(
				"branch %q does not contain parent %q; rebase the branch chain before adopting it",
				branchName,
				parentRef,
			)
		}
		branches = append(branches, state.Branch{
			Name: branchName,
			Base: parentSHA,
			Head: headSHA,
		})
		parentRef = "refs/heads/" + branchName
	}

	stack := state.Stack{
		Name:     options.Name,
		Remote:   options.Remote,
		Trunk:    options.Trunk,
		Branches: branches,
	}
	if m.DryRun {
		return &stack, nil
	}
	if err := m.Repository.ConfigureRerere(ctx); err != nil {
		return nil, err
	}
	file.Stacks = append(file.Stacks, stack)
	if err := locked.Save(file); err != nil {
		return nil, err
	}
	return &stack, nil
}

// Add creates a worktree on top of the current stack and records the branch.
func (m *Manager) Add(ctx context.Context, options AddOptions) (*state.Branch, error) {
	if options.Branch == "" {
		return nil, errors.New("branch name is required")
	}
	locked, file, stack, err := m.lockedStack(ctx, options.StackName)
	if err != nil {
		return nil, err
	}
	defer func() {
		_ = locked.Close()
	}()
	if file.Rebase != nil {
		return nil, fmt.Errorf("rebase for stack %s must be continued or aborted", file.Rebase.StackName)
	}
	if _, exists := file.FindStackForBranch(options.Branch); exists {
		return nil, fmt.Errorf("branch %q already belongs to a stack", options.Branch)
	}
	if len(stack.Branches) == 0 {
		return nil, fmt.Errorf("stack %q has no branches", stack.Name)
	}
	if options.Path == "" {
		options.Path = filepath.Join(m.Repository.Container, worktreeSlug(options.Branch))
	} else if !filepath.IsAbs(options.Path) {
		options.Path = filepath.Join(m.Repository.Container, options.Path)
	}
	if _, statErr := os.Stat(options.Path); statErr == nil {
		return nil, fmt.Errorf("worktree path already exists: %s", options.Path)
	} else if !errors.Is(statErr, os.ErrNotExist) {
		return nil, fmt.Errorf("checking worktree path %s: %w", options.Path, statErr)
	}

	top := &stack.Branches[len(stack.Branches)-1]
	topHead, err := m.Repository.Head(ctx, "refs/heads/"+top.Name)
	if err != nil {
		return nil, err
	}
	branch := state.Branch{Name: options.Branch, Base: topHead, Head: topHead}
	if m.DryRun {
		return &branch, nil
	}
	if err := m.Repository.CreateWorktree(
		ctx,
		options.Branch,
		options.Path,
		top.Name,
	); err != nil {
		return nil, err
	}
	stack.Branches = append(stack.Branches, branch)
	if err := locked.Save(file); err != nil {
		return nil, err
	}
	return &branch, nil
}

// Status returns live status for all stacks or one selected stack.
func (m *Manager) Status(
	ctx context.Context,
	stackName string,
) ([]StackStatus, error) {
	locked, err := m.Store.Lock()
	if err != nil {
		return nil, err
	}
	defer func() {
		_ = locked.Close()
	}()
	file, err := locked.Load()
	if err != nil {
		return nil, err
	}

	candidates := file.Stacks
	if stackName != "" {
		stack, exists := file.FindStack(stackName)
		if !exists {
			return nil, fmt.Errorf("stack %q not found", stackName)
		}
		candidates = []state.Stack{*stack}
	}
	statuses := make([]StackStatus, 0, len(candidates))
	for _, stack := range candidates {
		stackStatus := StackStatus{
			Name:     stack.Name,
			Remote:   stack.Remote,
			Trunk:    stack.Trunk,
			Branches: make([]BranchStatus, 0, len(stack.Branches)),
		}
		for _, branch := range stack.Branches {
			head, headErr := m.Repository.Head(ctx, "refs/heads/"+branch.Name)
			if headErr != nil {
				head = ""
			}
			worktree, exists, worktreeErr := m.Repository.WorktreeForBranch(ctx, branch.Name)
			if worktreeErr != nil {
				return nil, worktreeErr
			}
			clean := false
			if exists {
				clean, err = m.Repository.IsClean(ctx, worktree.Path)
				if err != nil {
					return nil, err
				}
			}
			stackStatus.Branches = append(stackStatus.Branches, BranchStatus{
				Name:        branch.Name,
				Worktree:    worktree.Path,
				Clean:       clean,
				Head:        head,
				Base:        branch.Base,
				Drifted:     head != "" && head != branch.Head,
				PullRequest: branch.PullRequest,
			})
		}
		statuses = append(statuses, stackStatus)
	}
	return statuses, nil
}

// Rebase fetches trunk and cascades rebases through active branch worktrees.
func (m *Manager) Rebase(ctx context.Context, options RebaseOptions) error {
	locked, file, stack, err := m.lockedStack(ctx, options.StackName)
	if err != nil {
		return err
	}
	defer func() {
		_ = locked.Close()
	}()
	if file.Rebase != nil {
		return fmt.Errorf("rebase for stack %s must be continued or aborted", file.Rebase.StackName)
	}
	if options.Fetch {
		if err := m.Repository.Fetch(ctx, stack.Remote); err != nil {
			return err
		}
	}
	active := activeBranchIndices(stack)
	if len(active) == 0 {
		return fmt.Errorf("stack %q has no active branches", stack.Name)
	}
	if err := m.validateCleanWorktrees(ctx, stack, active); err != nil {
		return err
	}
	if m.DryRun {
		return nil
	}

	originalBranches := make(map[string]string, len(stack.Branches))
	for _, branch := range stack.Branches {
		head, err := m.Repository.Head(ctx, "refs/heads/"+branch.Name)
		if err != nil {
			return err
		}
		originalBranches[branch.Name] = head
	}
	file.Rebase = &state.RebaseSession{
		StackName:        stack.Name,
		CurrentIndex:     active[0],
		OriginalBranches: originalBranches,
		OriginalStack:    state.CloneStack(*stack),
	}
	if err := locked.Save(file); err != nil {
		return err
	}
	return m.runCascade(ctx, locked, file, stack, active[0], false)
}

// Continue resumes a paused cascading rebase.
func (m *Manager) Continue(ctx context.Context) error {
	locked, err := m.Store.Lock()
	if err != nil {
		return err
	}
	defer func() {
		_ = locked.Close()
	}()
	file, err := locked.Load()
	if err != nil {
		return err
	}
	if file.Rebase == nil {
		return errors.New("no rebase is in progress")
	}
	stack, exists := file.FindStack(file.Rebase.StackName)
	if !exists {
		return fmt.Errorf("stack %q from rebase state no longer exists", file.Rebase.StackName)
	}
	return m.runCascade(
		ctx,
		locked,
		file,
		stack,
		file.Rebase.CurrentIndex,
		true,
	)
}

// Abort stops a paused rebase and restores every branch to its original SHA.
func (m *Manager) Abort(ctx context.Context) error {
	locked, err := m.Store.Lock()
	if err != nil {
		return err
	}
	defer func() {
		_ = locked.Close()
	}()
	file, err := locked.Load()
	if err != nil {
		return err
	}
	if file.Rebase == nil {
		return errors.New("no rebase is in progress")
	}
	session := file.Rebase
	stack, exists := file.FindStack(session.StackName)
	if !exists {
		return fmt.Errorf("stack %q from rebase state no longer exists", session.StackName)
	}

	currentBranch := stack.Branches[session.CurrentIndex]
	currentWorktreePath := session.CurrentWorktree
	if currentWorktreePath == "" {
		currentWorktree, exists, err := m.Repository.WorktreeForBranch(
			ctx,
			currentBranch.Name,
		)
		if err != nil {
			return err
		}
		if exists {
			currentWorktreePath = currentWorktree.Path
		}
	}
	if currentWorktreePath != "" &&
		m.Repository.RebaseInProgress(ctx, currentWorktreePath) {
		if err := m.Repository.AbortRebase(ctx, currentWorktreePath); err != nil {
			return err
		}
	}
	for branchName, sha := range session.OriginalBranches {
		worktree, branchExists, worktreeErr := m.Repository.WorktreeForBranch(ctx, branchName)
		if worktreeErr != nil {
			return worktreeErr
		}
		if !branchExists {
			return fmt.Errorf("branch %q no longer has a worktree", branchName)
		}
		if err := m.Repository.ResetHard(ctx, worktree.Path, sha); err != nil {
			return err
		}
	}
	*stack = state.CloneStack(session.OriginalStack)
	file.Rebase = nil
	return locked.Save(file)
}

// Push safely force-pushes active stack branches with explicit leases.
func (m *Manager) Push(ctx context.Context, stackName string) error {
	locked, file, stack, err := m.lockedStack(ctx, stackName)
	if err != nil {
		return err
	}
	defer func() {
		_ = locked.Close()
	}()
	if file.Rebase != nil {
		return fmt.Errorf("rebase for stack %s must be continued or aborted", file.Rebase.StackName)
	}
	return m.pushLocked(ctx, locked, file, stack)
}

// Refresh updates pull request metadata for every branch in a stack.
func (m *Manager) Refresh(ctx context.Context, stackName string) error {
	locked, file, stack, err := m.lockedStack(ctx, stackName)
	if err != nil {
		return err
	}
	defer func() {
		_ = locked.Close()
	}()
	return m.refreshLocked(ctx, locked, file, stack)
}

// Submit pushes active branches and creates or updates their GitHub Stack.
func (m *Manager) Submit(ctx context.Context, stackName string) error {
	locked, file, stack, err := m.lockedStack(ctx, stackName)
	if err != nil {
		return err
	}
	defer func() {
		_ = locked.Close()
	}()
	if file.Rebase != nil {
		return fmt.Errorf("rebase for stack %s must be continued or aborted", file.Rebase.StackName)
	}
	if err := m.pushLocked(ctx, locked, file, stack); err != nil {
		return err
	}
	repository, err := m.GitHub.Repository(ctx, stack.Remote)
	if err != nil {
		return err
	}
	branches := make([]string, 0, len(stack.Branches))
	for _, branch := range stack.Branches {
		branches = append(branches, branch.Name)
	}
	if m.DryRun {
		return nil
	}
	if err := m.GitHub.Link(
		ctx,
		repository,
		stack.Trunk,
		branches,
	); err != nil {
		return err
	}
	return m.refreshLocked(ctx, locked, file, stack)
}

// Doctor verifies authentication and repository preview availability.
func (m *Manager) Doctor(
	ctx context.Context,
	stackName string,
) (map[string]string, error) {
	remote, err := m.doctorRemote(ctx, stackName)
	if err != nil {
		return nil, err
	}
	repository, err := m.GitHub.Repository(ctx, remote)
	if err != nil {
		return nil, err
	}
	if err := m.GitHub.Authenticate(ctx, repository.Host); err != nil {
		return nil, err
	}
	if err := m.GitHub.StacksAvailable(ctx, repository); err != nil {
		return nil, err
	}
	return map[string]string{
		"commonDir":        m.Repository.CommonDir,
		"container":        m.Repository.Container,
		"githubHost":       repository.Host,
		"githubRepository": repository.Slug(),
		"githubAuth":       "available",
	}, nil
}

func (m *Manager) doctorRemote(
	ctx context.Context,
	stackName string,
) (string, error) {
	locked, err := m.Store.Lock()
	if err != nil {
		return "", err
	}
	defer func() {
		_ = locked.Close()
	}()
	file, err := locked.Load()
	if err != nil {
		return "", err
	}
	if stackName != "" {
		stack, exists := file.FindStack(stackName)
		if !exists {
			return "", fmt.Errorf("stack %q not found", stackName)
		}
		return stack.Remote, nil
	}
	currentBranch, branchErr := m.Repository.CurrentBranch(ctx)
	if branchErr == nil {
		if stack, exists := file.FindStackForBranch(currentBranch); exists {
			return stack.Remote, nil
		}
	}
	if len(file.Stacks) == 1 {
		return file.Stacks[0].Remote, nil
	}
	return "origin", nil
}

func (m *Manager) lockedStack(
	ctx context.Context,
	stackName string,
) (*state.LockedStore, *state.File, *state.Stack, error) {
	locked, err := m.Store.Lock()
	if err != nil {
		return nil, nil, nil, err
	}
	file, err := locked.Load()
	if err != nil {
		_ = locked.Close()
		return nil, nil, nil, err
	}
	stack, err := m.selectStack(ctx, file, stackName)
	if err != nil {
		_ = locked.Close()
		return nil, nil, nil, err
	}
	return locked, file, stack, nil
}

func (m *Manager) selectStack(
	ctx context.Context,
	file *state.File,
	stackName string,
) (*state.Stack, error) {
	if stackName != "" {
		stack, exists := file.FindStack(stackName)
		if !exists {
			return nil, fmt.Errorf("stack %q not found", stackName)
		}
		return stack, nil
	}
	currentBranch, err := m.Repository.CurrentBranch(ctx)
	if err == nil {
		if stack, exists := file.FindStackForBranch(currentBranch); exists {
			return stack, nil
		}
	}
	if len(file.Stacks) == 1 {
		return &file.Stacks[0], nil
	}
	if len(file.Stacks) == 0 {
		return nil, errors.New("no stacks are initialized")
	}
	return nil, errors.New("select a stack with --stack")
}

func (m *Manager) runCascade(
	ctx context.Context,
	locked *state.LockedStore,
	file *state.File,
	stack *state.Stack,
	startIndex int,
	continueCurrent bool,
) error {
	active := activeBranchIndices(stack)
	for _, branchIndex := range active {
		if branchIndex < startIndex {
			continue
		}
		branch := &stack.Branches[branchIndex]
		worktreePath := ""
		if branchIndex == startIndex && file.Rebase.CurrentWorktree != "" {
			worktreePath = file.Rebase.CurrentWorktree
		} else {
			worktree, exists, err := m.Repository.WorktreeForBranch(ctx, branch.Name)
			if err != nil {
				return err
			}
			if !exists {
				return fmt.Errorf("branch %q no longer has a worktree", branch.Name)
			}
			worktreePath = worktree.Path
		}
		file.Rebase.CurrentIndex = branchIndex
		file.Rebase.CurrentWorktree = worktreePath
		if err := locked.Save(file); err != nil {
			return err
		}

		newBaseRef := m.activeBaseRef(stack, branchIndex)
		newBaseSHA, err := m.Repository.Head(ctx, newBaseRef)
		if err != nil {
			return err
		}
		if continueCurrent && branchIndex == startIndex &&
			m.Repository.RebaseInProgress(ctx, worktreePath) {
			err = m.Repository.ContinueRebase(ctx, worktreePath)
		} else {
			err = m.Repository.RebaseOnto(
				ctx,
				worktreePath,
				newBaseSHA,
				branch.Base,
			)
		}
		if err != nil {
			if saveErr := locked.Save(file); saveErr != nil {
				return errors.Join(err, saveErr)
			}
			return &RebaseConflict{
				StackName: stack.Name,
				Branch:    branch.Name,
				Worktree:  worktreePath,
			}
		}

		head, err := m.Repository.Head(ctx, "refs/heads/"+branch.Name)
		if err != nil {
			return err
		}
		branch.Base = newBaseSHA
		branch.Head = head
		continueCurrent = false
		if err := locked.Save(file); err != nil {
			return err
		}
	}
	file.Rebase = nil
	return locked.Save(file)
}

func (m *Manager) activeBaseRef(stack *state.Stack, branchIndex int) string {
	for index := branchIndex - 1; index >= 0; index-- {
		if !branchMerged(stack.Branches[index]) {
			return "refs/heads/" + stack.Branches[index].Name
		}
	}
	return gitrepo.RemoteRef(stack.Remote, stack.Trunk)
}

func (m *Manager) validateCleanWorktrees(
	ctx context.Context,
	stack *state.Stack,
	indices []int,
) error {
	for _, index := range indices {
		branch := stack.Branches[index]
		worktree, exists, err := m.Repository.WorktreeForBranch(ctx, branch.Name)
		if err != nil {
			return err
		}
		if !exists {
			return fmt.Errorf("branch %q is not checked out in a worktree", branch.Name)
		}
		clean, err := m.Repository.IsClean(ctx, worktree.Path)
		if err != nil {
			return err
		}
		if !clean {
			return fmt.Errorf("worktree for branch %q has uncommitted changes: %s",
				branch.Name, worktree.Path)
		}
	}
	return nil
}

func (m *Manager) pushLocked(
	ctx context.Context,
	locked *state.LockedStore,
	file *state.File,
	stack *state.Stack,
) error {
	active := activeBranchIndices(stack)
	if len(active) == 0 {
		return fmt.Errorf("stack %q has no active branches", stack.Name)
	}
	if err := m.validateCleanWorktrees(ctx, stack, active); err != nil {
		return err
	}
	if err := m.Repository.Fetch(ctx, stack.Remote); err != nil {
		return err
	}
	branches := make([]string, 0, len(active))
	for _, index := range active {
		branch := &stack.Branches[index]
		head, err := m.Repository.Head(ctx, "refs/heads/"+branch.Name)
		if err != nil {
			return err
		}
		branch.Head = head
		branches = append(branches, branch.Name)
	}
	if m.DryRun {
		return nil
	}
	if err := m.Repository.PushStack(ctx, stack.Remote, branches); err != nil {
		return err
	}
	return locked.Save(file)
}

func (m *Manager) refreshLocked(
	ctx context.Context,
	locked *state.LockedStore,
	file *state.File,
	stack *state.Stack,
) error {
	repository, err := m.GitHub.Repository(ctx, stack.Remote)
	if err != nil {
		return err
	}
	for index := range stack.Branches {
		pullRequest, err := m.GitHub.PullRequest(
			ctx,
			repository,
			stack.Branches[index].Name,
		)
		if err != nil {
			return err
		}
		stack.Branches[index].PullRequest = pullRequest
	}
	if m.DryRun {
		return nil
	}
	return locked.Save(file)
}

func activeBranchIndices(stack *state.Stack) []int {
	indices := make([]int, 0, len(stack.Branches))
	for index, branch := range stack.Branches {
		if !branchMerged(branch) {
			indices = append(indices, index)
		}
	}
	return indices
}

func branchMerged(branch state.Branch) bool {
	return branch.PullRequest != nil && branch.PullRequest.Merged
}

func worktreeSlug(branch string) string {
	parts := strings.Split(branch, "/")
	candidate := parts[len(parts)-1]
	candidate = unsafePathCharacters.ReplaceAllString(candidate, "-")
	candidate = strings.Trim(candidate, "-.")
	if candidate == "" {
		candidate = strings.Join(parts, "-")
		candidate = unsafePathCharacters.ReplaceAllString(candidate, "-")
	}
	return candidate
}
