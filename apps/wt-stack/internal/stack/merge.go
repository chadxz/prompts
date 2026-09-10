package stack

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/chadxz/prompts/apps/wt-stack/internal/github"
	"github.com/chadxz/prompts/apps/wt-stack/internal/state"
)

// MergeOptions selects a local stack prefix or resumes a remote request by ID.
// An empty Through selects the top branch. Resume requires PullRequest.
type MergeOptions struct {
	StackName   string
	Through     string
	Method      string
	Timeout     time.Duration
	Resume      string
	PullRequest int
}

// Merge validates the selected published branches and requests an async merge.
// A pending result can be resumed by UUID. Polling never resubmits a merge and
// enqueued is terminal for this operation, not proof that the PRs have landed.
func (m *Manager) Merge(ctx context.Context, options MergeOptions) (*github.MergeResult, error) {
	if options.Timeout <= 0 {
		return nil, errors.New("merge timeout must be positive")
	}
	if options.Method != "" && options.Method != "merge" && options.Method != "squash" && options.Method != "rebase" {
		return nil, errors.New("merge method must be merge, squash, or rebase")
	}
	if options.Resume != "" {
		if options.PullRequest <= 0 || options.Through != "" || options.Method != "" {
			return nil, errors.New("--resume requires --pr and cannot be combined with --through or --merge-method")
		}
	} else if options.PullRequest != 0 {
		return nil, errors.New("--pr is only valid with --resume")
	}
	locked, file, stack, err := m.lockedStack(ctx, options.StackName)
	if err != nil {
		return nil, err
	}
	defer func() { _ = locked.Close() }()
	if file.Rebase != nil {
		return nil, fmt.Errorf("rebase for stack %s must be continued or aborted", file.Rebase.StackName)
	}
	repository, err := m.github.Repository(ctx, stack.Remote)
	if err != nil {
		return nil, err
	}
	var result *github.MergeResult
	if options.Resume != "" {
		result = &github.MergeResult{Status: "pending", PullRequest: options.PullRequest, UUID: options.Resume}
		observed, pollErr := m.github.PollMerge(ctx, repository, options.PullRequest, options.Resume)
		if pollErr != nil {
			return result, pollErr
		}
		result = observed
	} else {
		members, head, targetErr := m.mergeMembers(ctx, repository, stack, options.Through)
		if targetErr != nil {
			return nil, targetErr
		}
		if err := m.github.ValidateMergeScope(ctx, repository, members); err != nil {
			return nil, err
		}
		number := members[len(members)-1].Number
		if m.dryRun {
			return &github.MergeResult{Status: "planned", PullRequest: number, HeadSHA: head}, nil
		}
		result, err = m.github.StartMerge(ctx, repository, number, head, options.Method)
	}
	if err != nil {
		return result, err
	}
	if result.Existing {
		return result, nil
	} // Existing options may differ; require explicit resume.
	if m.dryRun {
		return result, nil
	}
	return m.waitForMerge(ctx, repository, result, options.Timeout)
}

func (m *Manager) mergeMembers(ctx context.Context, repository github.Repository, stack *state.Stack, through string) ([]state.PullRequest, string, error) {
	last := len(stack.Branches) - 1
	if through != "" {
		last = -1
		for index, branch := range stack.Branches {
			if branch.Name == through {
				last = index
				break
			}
		}
	}
	if last < 0 {
		return nil, "", errors.New("merge target is not a branch in the selected stack")
	}
	members := make([]state.PullRequest, 0, last+1)
	expectedBase := stack.Trunk
	head := ""
	previousHead := ""
	active := make([]int, 0, last+1)
	for index, branch := range stack.Branches[:last+1] {
		pr, err := m.github.PullRequest(ctx, repository, branch.Name)
		if err != nil {
			return nil, "", err
		}
		if pr == nil || pr.Number <= 0 {
			return nil, "", fmt.Errorf("branch %s has no published pull request; sync before merging", branch.Name)
		}
		if pr.Merged {
			if index == last {
				return nil, "", fmt.Errorf("pull request #%d is already merged; select an active branch", pr.Number)
			}
			members = append(members, *pr)
			continue
		}
		if pr.State != "open" || pr.Draft {
			return nil, "", fmt.Errorf("pull request #%d must be open and ready for review", pr.Number)
		}
		if pr.Base != expectedBase {
			return nil, "", fmt.Errorf("pull request #%d targets %s instead of %s; sync before merging", pr.Number, pr.Base, expectedBase)
		}
		head, err = m.repository.Head(ctx, "refs/heads/"+branch.Name)
		if err != nil {
			return nil, "", err
		}
		if head == "" || head != pr.HeadSHA {
			return nil, "", fmt.Errorf("pull request #%d head differs from local branch %s; sync before merging", pr.Number, branch.Name)
		}
		if previousHead != "" {
			contains, err := m.repository.IsAncestor(ctx, previousHead, head)
			if err != nil {
				return nil, "", err
			}
			if !contains {
				return nil, "", fmt.Errorf("branch %s does not contain its parent; sync before merging", branch.Name)
			}
		}
		previousHead = head
		active = append(active, index)
		members = append(members, *pr)
		expectedBase = branch.Name
	}
	if err := m.validateCleanWorktrees(ctx, stack, active); err != nil {
		return nil, "", err
	}
	return members, head, nil
}

func (m *Manager) waitForMerge(ctx context.Context, repository github.Repository, result *github.MergeResult, timeout time.Duration) (*github.MergeResult, error) {
	pollCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	for result.Status == "pending" {
		timer := time.NewTimer(time.Second)
		select {
		case <-pollCtx.Done():
			timer.Stop()
			if ctx.Err() != nil {
				return result, ctx.Err()
			}
			return result, nil
		case <-timer.C:
		}
		next, err := m.github.PollMerge(pollCtx, repository, result.PullRequest, result.UUID)
		if err != nil {
			if ctx.Err() == nil && errors.Is(pollCtx.Err(), context.DeadlineExceeded) {
				return result, nil
			}
			return result, err
		}
		result = next
	}
	if result.Status == "failed" {
		return result, fmt.Errorf("merge failed: %s", result.Message)
	}
	return result, nil
}
