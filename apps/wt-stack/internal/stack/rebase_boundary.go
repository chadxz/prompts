package stack

import (
	"context"
	"fmt"

	"github.com/chadxz/prompts/apps/wt-stack/internal/gitrepo"
	"github.com/chadxz/prompts/apps/wt-stack/internal/state"
)

// rebaseBoundaries preflights the entire cascade before any branch is rewritten.
func (m *Manager) rebaseBoundaries(ctx context.Context, stack *state.Stack, indices []int) (map[int]string, error) {
	boundaries := make(map[int]string, len(indices))
	for _, index := range indices {
		branch := stack.Branches[index]
		head, err := m.repository.Head(ctx, "refs/heads/"+branch.Name)
		if err != nil {
			return nil, err
		}
		parent := gitrepo.RemoteRef(stack.Remote, stack.Trunk)
		if index > 0 {
			parent = "refs/heads/" + stack.Branches[index-1].Name
		}
		base, err := m.resolveRebaseBoundary(ctx, branch.Base, parent, head, branch.Name)
		if err != nil {
			return nil, err
		}
		boundaries[index] = base
	}
	return boundaries, nil
}

func (m *Manager) resolveRebaseBoundary(ctx context.Context, recorded, parent, head, branch string) (string, error) {
	valid := func(candidate string) bool {
		if candidate == "" {
			return false
		}
		ok, err := m.repository.IsAncestor(ctx, candidate, head)
		return err == nil && ok
	}
	if valid(recorded) {
		return recorded, nil
	}
	if current, err := m.repository.Head(ctx, parent); err == nil && valid(current) {
		return current, nil
	}
	if fork, err := m.repository.ForkPoint(ctx, parent, "refs/heads/"+branch); err == nil && valid(fork) {
		return fork, nil
	}
	return "", fmt.Errorf("cannot determine a safe previous base for %s; restore its recorded base or rebase the branch manually before retrying", branch)
}
