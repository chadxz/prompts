package github

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"slices"
	"strings"

	"github.com/chadxz/prompts/apps/wt-stack/internal/state"
)

type remoteStackPullRequest struct {
	Number int `json:"number"`
}

type remoteStack struct {
	ID           int                      `json:"id"`
	Number       int                      `json:"number"`
	PullRequests []remoteStackPullRequest `json:"pull_requests"`
}

type stackRequest struct {
	PullRequests []int `json:"pull_requests"`
}

// Link creates pull requests and creates or additively updates their Stack.
func (c *Client) Link(
	ctx context.Context,
	repository Repository,
	trunk string,
	branches []string,
) error {
	if len(branches) == 0 {
		return errors.New("stack has no branches")
	}

	pullRequests := make([]*state.PullRequest, len(branches))
	knownNumbers := make([]int, 0, len(branches))
	for index, branch := range branches {
		pullRequest, err := c.PullRequest(ctx, repository, branch)
		if err != nil {
			return err
		}
		if pullRequest != nil {
			if !pullRequest.Merged &&
				!strings.EqualFold(pullRequest.State, "open") {
				pullRequest = nil
			} else if !pullRequest.Merged {
				knownNumbers = append(knownNumbers, pullRequest.Number)
			}
		}
		pullRequests[index] = pullRequest
	}

	if len(branches) == 1 {
		_, err := c.ensurePullRequests(
			ctx,
			repository,
			trunk,
			branches,
			pullRequests,
		)
		return err
	}

	stacks, err := c.listStacks(ctx, repository)
	if err != nil {
		return fmt.Errorf("listing GitHub Stacks: %w", err)
	}
	matched, err := matchingStack(stacks, knownNumbers)
	if err != nil {
		return err
	}
	if matched != nil {
		if err := validateAdditiveUpdate(matched, pullRequests); err != nil {
			return err
		}
	}

	resolved, err := c.ensurePullRequests(
		ctx,
		repository,
		trunk,
		branches,
		pullRequests,
	)
	if err != nil {
		return err
	}
	desired := desiredStackPullRequests(matched, resolved)
	return c.upsertStack(ctx, repository, matched, desired)
}

// Unstack removes a matching Stack from GitHub.
//
// The returned boolean is false when GitHub preserves pull requests that are
// queued for merge or have auto-merge enabled.
func (c *Client) Unstack(
	ctx context.Context,
	repository Repository,
	pullRequestNumbers []int,
) (bool, error) {
	if len(pullRequestNumbers) == 0 {
		return true, nil
	}
	stacks, err := c.listStacks(ctx, repository)
	if err != nil {
		return false, fmt.Errorf("listing GitHub Stacks: %w", err)
	}
	matched := stacksContainingPullRequests(stacks, pullRequestNumbers)
	if len(matched) == 0 {
		return true, nil
	}

	dissolved := true
	for _, stack := range matched {
		var remaining remoteStack
		path := fmt.Sprintf(
			"repos/%s/stacks/%d/unstack",
			repository.Slug(),
			stack.Number,
		)
		if _, err := c.request(
			ctx,
			repository,
			http.MethodPost,
			path,
			nil,
			&remaining,
		); err != nil {
			var apiErr *APIError
			if errors.As(err, &apiErr) &&
				apiErr.StatusCode == http.StatusNotFound {
				continue
			}
			return false, fmt.Errorf("unstacking GitHub Stack #%d: %w",
				stack.Number, err)
		}
		if remaining.Number != 0 ||
			remaining.ID != 0 ||
			len(remaining.PullRequests) != 0 {
			dissolved = false
		}
	}
	return dissolved, nil
}

// StacksAvailable verifies that the repository has the Stacked PRs preview.
func (c *Client) StacksAvailable(
	ctx context.Context,
	repository Repository,
) error {
	if _, err := c.listStacks(ctx, repository); err != nil {
		return fmt.Errorf("checking Stacked PRs availability: %w", err)
	}
	return nil
}

func (c *Client) listStacks(
	ctx context.Context,
	repository Repository,
) ([]remoteStack, error) {
	stacks := make([]remoteStack, 0)
	path := "repos/" + repository.Slug() + "/stacks?per_page=100"
	for path != "" {
		var page []remoteStack
		headers, err := c.request(
			ctx,
			repository,
			http.MethodGet,
			path,
			nil,
			&page,
		)
		if err != nil {
			return nil, err
		}
		stacks = append(stacks, page...)
		path = nextPagePath(headers.Get("Link"))
	}
	return stacks, nil
}

func (c *Client) ensurePullRequests(
	ctx context.Context,
	repository Repository,
	trunk string,
	branches []string,
	pullRequests []*state.PullRequest,
) ([]*state.PullRequest, error) {
	resolved := make([]*state.PullRequest, len(branches))
	expectedBase := trunk
	for index, branch := range branches {
		pullRequest := pullRequests[index]
		if pullRequest == nil {
			var err error
			pullRequest, err = c.createPullRequest(
				ctx,
				repository,
				branch,
				expectedBase,
			)
			if err != nil {
				return nil, fmt.Errorf(
					"creating pull request for %s: %w",
					branch,
					err,
				)
			}
		}

		resolved[index] = pullRequest
		if pullRequest.Merged {
			continue
		}
		expectedBase = branch
	}

	expectedBase = trunk
	for index, branch := range branches {
		pullRequest := resolved[index]
		if pullRequest.Merged {
			continue
		}
		if pullRequest.Base != expectedBase {
			if err := c.updatePullRequestBase(
				ctx,
				repository,
				pullRequest.Number,
				expectedBase,
			); err != nil {
				return nil, fmt.Errorf(
					"updating base for pull request #%d: %w",
					pullRequest.Number,
					err,
				)
			}
			pullRequest.Base = expectedBase
		}
		expectedBase = branch
	}
	return resolved, nil
}

func (c *Client) updatePullRequestBase(
	ctx context.Context,
	repository Repository,
	number int,
	base string,
) error {
	request := struct {
		Base string `json:"base"`
	}{Base: base}
	_, err := c.request(
		ctx,
		repository,
		http.MethodPatch,
		fmt.Sprintf("repos/%s/pulls/%d", repository.Slug(), number),
		request,
		nil,
	)
	return err
}

func (c *Client) upsertStack(
	ctx context.Context,
	repository Repository,
	existing *remoteStack,
	desired []int,
) error {
	if existing == nil {
		_, err := c.request(
			ctx,
			repository,
			http.MethodPost,
			"repos/"+repository.Slug()+"/stacks",
			stackRequest{PullRequests: desired},
			nil,
		)
		return err
	}

	current := existing.numbers()
	if slices.Equal(current, desired) {
		return nil
	}
	if len(current) > len(desired) ||
		!slices.Equal(current, desired[:len(current)]) {
		return fmt.Errorf(
			"cannot update Stack #%d: existing pull requests are not an ordered prefix",
			existing.Number,
		)
	}
	_, err := c.request(
		ctx,
		repository,
		http.MethodPost,
		fmt.Sprintf(
			"repos/%s/stacks/%d/add",
			repository.Slug(),
			existing.Number,
		),
		stackRequest{PullRequests: desired[len(current):]},
		nil,
	)
	return err
}

func matchingStack(
	stacks []remoteStack,
	pullRequestNumbers []int,
) (*remoteStack, error) {
	wanted := make(map[int]struct{}, len(pullRequestNumbers))
	for _, number := range pullRequestNumbers {
		wanted[number] = struct{}{}
	}

	var matched *remoteStack
	for index := range stacks {
		for _, number := range stacks[index].numbers() {
			if _, exists := wanted[number]; !exists {
				continue
			}
			if matched != nil && matched.Number != stacks[index].Number {
				return nil, errors.New(
					"pull requests belong to multiple Stacks; unstack them first",
				)
			}
			matched = &stacks[index]
			break
		}
	}
	return matched, nil
}

func stacksContainingPullRequests(
	stacks []remoteStack,
	pullRequestNumbers []int,
) []remoteStack {
	wanted := make(map[int]struct{}, len(pullRequestNumbers))
	for _, number := range pullRequestNumbers {
		wanted[number] = struct{}{}
	}
	matched := make([]remoteStack, 0)
	for _, stack := range stacks {
		for _, number := range stack.numbers() {
			if _, exists := wanted[number]; !exists {
				continue
			}
			matched = append(matched, stack)
			break
		}
	}
	return matched
}

func validateAdditiveUpdate(
	stack *remoteStack,
	pullRequests []*state.PullRequest,
) error {
	current := stack.numbers()
	currentIndex := 0
	for _, pullRequest := range pullRequests {
		if currentIndex == len(current) {
			break
		}
		if pullRequest != nil &&
			pullRequest.Number == current[currentIndex] {
			currentIndex++
			continue
		}
		if pullRequest != nil && pullRequest.Merged {
			continue
		}
		if pullRequest == nil ||
			pullRequest.Number != current[currentIndex] {
			return fmt.Errorf(
				"cannot update Stack #%d: existing pull requests are not an ordered prefix",
				stack.Number,
			)
		}
	}
	if currentIndex != len(current) {
		return fmt.Errorf(
			"cannot update Stack #%d without pull request #%d",
			stack.Number,
			current[currentIndex],
		)
	}
	return nil
}

func desiredStackPullRequests(
	existing *remoteStack,
	pullRequests []*state.PullRequest,
) []int {
	if existing == nil {
		desired := make([]int, 0, len(pullRequests))
		for _, pullRequest := range pullRequests {
			if !pullRequest.Merged {
				desired = append(desired, pullRequest.Number)
			}
		}
		return desired
	}

	desired := slices.Clone(existing.numbers())
	included := make(map[int]struct{}, len(desired))
	for _, number := range desired {
		included[number] = struct{}{}
	}
	for _, pullRequest := range pullRequests {
		if pullRequest.Merged {
			continue
		}
		if _, exists := included[pullRequest.Number]; exists {
			continue
		}
		desired = append(desired, pullRequest.Number)
		included[pullRequest.Number] = struct{}{}
	}
	return desired
}

func nextPagePath(linkHeader string) string {
	for _, value := range strings.Split(linkHeader, ",") {
		sections := strings.Split(value, ";")
		if len(sections) < 2 ||
			!strings.Contains(strings.Join(sections[1:], ";"), `rel="next"`) {
			continue
		}
		target := strings.Trim(strings.TrimSpace(sections[0]), "<>")
		parsed, err := url.Parse(target)
		if err != nil {
			return ""
		}
		return strings.TrimLeft(parsed.RequestURI(), "/")
	}
	return ""
}

func (s *remoteStack) numbers() []int {
	numbers := make([]int, 0, len(s.PullRequests))
	for _, pullRequest := range s.PullRequests {
		numbers = append(numbers, pullRequest.Number)
	}
	return numbers
}
