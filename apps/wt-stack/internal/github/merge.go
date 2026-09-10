package github

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"regexp"
	"slices"

	"github.com/chadxz/prompts/apps/wt-stack/internal/state"
)

var mergeRequestID = regexp.MustCompile(`^[A-Za-z0-9-]+$`)

// MergeResult reports an async merge without conflating queue admission with landing.
// UUID and PullRequest identify a pending operation for read-only resumption.
type MergeResult struct {
	Status      string `json:"status"`
	PullRequest int    `json:"pullRequest"`
	UUID        string `json:"uuid,omitempty"`
	Message     string `json:"message,omitempty"`
	HeadSHA     string `json:"headSha,omitempty"`
	Existing    bool   `json:"existing,omitempty"`
}

type asyncMergeWire struct {
	Status  string `json:"status"`
	Details struct {
		UUID            string `json:"uuid"`
		Message         string `json:"message"`
		ExpectedHeadSHA string `json:"expected_head_sha"`
	} `json:"details"`
}

// ValidateMergeScope ensures the target cannot merge unselected remote members.
// Already merged members may remain in GitHub's stack history.
func (c *Client) ValidateMergeScope(ctx context.Context, repository Repository, members []state.PullRequest) error {
	if len(members) == 0 {
		return errors.New("no pull requests selected for merge")
	}
	target := members[len(members)-1].Number
	stacks, err := c.listStacks(ctx, repository)
	if err != nil {
		return err
	}
	expected := make([]int, 0, len(members))
	known := make(map[int]bool, len(members))
	for _, member := range members {
		known[member.Number] = member.Merged
		if !member.Merged {
			expected = append(expected, member.Number)
		}
	}
	for _, stack := range stacks {
		numbers := stack.numbers()
		index := slices.Index(numbers, target)
		if index < 0 {
			continue
		}
		actual := make([]int, 0, index+1)
		for _, number := range numbers[:index+1] {
			merged, exists := known[number]
			if !exists {
				return fmt.Errorf("remote Stack contains unselected pull request #%d below #%d", number, target)
			}
			if !merged {
				actual = append(actual, number)
			}
		}
		if !slices.Equal(expected, actual) {
			return errors.New("remote Stack order differs from selected branches; sync before merging")
		}
		return nil
	}
	// A single published branch need not belong to a GitHub Stack.
	if len(expected) == 1 {
		return nil
	}
	return errors.New("selected pull requests do not belong to a remote Stack; sync before merging")
}

// StartMerge submits one head-guarded merge request; it never retries a mutation
// on transient failure. A pre-existing request is returned for explicit resumption.
func (c *Client) StartMerge(ctx context.Context, repository Repository, number int, sha, method string) (*MergeResult, error) {
	if number <= 0 || sha == "" {
		return nil, errors.New("merge requires a pull request and expected head SHA")
	}
	if method != "" && method != "merge" && method != "squash" && method != "rebase" {
		return nil, errors.New("invalid merge method")
	}
	body := struct {
		SHA    string `json:"sha"`
		Method string `json:"merge_method,omitempty"`
		Action string `json:"merge_action"`
	}{SHA: sha, Method: method, Action: "default"}
	var wire asyncMergeWire
	_, err := c.requestWithStatuses(ctx, repository, http.MethodPut,
		fmt.Sprintf("repos/%s/pulls/%d/merge-async", repository.Slug(), number), body, &wire,
		[]int{http.StatusBadRequest, http.StatusConflict})
	var apiErr *APIError
	if err != nil && (!errors.As(err, &apiErr) || (apiErr.StatusCode != http.StatusBadRequest && apiErr.StatusCode != http.StatusConflict)) {
		return nil, fmt.Errorf("submitting async merge: %w", err)
	}
	result, decodeErr := mergeResult(number, wire)
	if decodeErr != nil {
		return nil, decodeErr
	}
	if apiErr != nil {
		if apiErr.StatusCode == http.StatusConflict {
			if result.Status != "pending" {
				return nil, errors.New("existing merge response is not pending")
			}
			result.Existing = true
		} else if result.Status != "failed" {
			return nil, errors.New("rejected merge response is not failed")
		}
	}
	if result.Status == "pending" && !result.Existing && result.HeadSHA != "" && result.HeadSHA != sha {
		return result, errors.New("merge response expected head differs from requested head; inspect the pending operation")
	}
	return result, nil
}

// PollMerge reads an existing operation, including terminal states.
func (c *Client) PollMerge(ctx context.Context, repository Repository, number int, uuid string) (*MergeResult, error) {
	if number <= 0 || !mergeRequestID.MatchString(uuid) {
		return nil, errors.New("resume requires a pull request number and valid request UUID")
	}
	var wire asyncMergeWire
	_, err := c.request(ctx, repository, http.MethodGet,
		fmt.Sprintf("repos/%s/pulls/%d/merge-async/%s", repository.Slug(), number, uuid), nil, &wire)
	if err != nil {
		return nil, fmt.Errorf("polling async merge %s: %w", uuid, err)
	}
	result, err := mergeResult(number, wire)
	if err != nil {
		return nil, err
	}
	result.UUID = uuid
	return result, nil
}

func mergeResult(number int, wire asyncMergeWire) (*MergeResult, error) {
	switch wire.Status {
	case "pending":
		if !mergeRequestID.MatchString(wire.Details.UUID) {
			return nil, errors.New("pending merge response has no valid UUID")
		}
	case "merged", "enqueued", "failed":
	default:
		return nil, fmt.Errorf("unknown async merge status %q", wire.Status)
	}
	return &MergeResult{Status: wire.Status, PullRequest: number, UUID: wire.Details.UUID,
		Message: wire.Details.Message, HeadSHA: wire.Details.ExpectedHeadSHA}, nil
}
