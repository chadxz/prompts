// Package github delegates remote Stack operations to the GitHub CLI and the
// gh-stack extension.
package github

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strconv"
	"strings"

	"github.com/chadxz/prompts/apps/wt-stack/internal/state"
)

// Client executes GitHub CLI commands in a repository worktree.
type Client struct {
	dir   string
	ghBin string
	out   io.Writer
	err   io.Writer
}

type pullRequestWire struct {
	Number      int     `json:"number"`
	State       string  `json:"state"`
	MergedAt    *string `json:"mergedAt"`
	URL         string  `json:"url"`
	BaseRefName string  `json:"baseRefName"`
	HeadRefName string  `json:"headRefName"`
}

// NewClient creates a GitHub CLI client rooted in a repository worktree.
func NewClient(dir string, out io.Writer, errOut io.Writer) *Client {
	ghBin := os.Getenv("WT_STACK_GH_BIN")
	if ghBin == "" {
		ghBin = "gh"
	}
	return &Client{dir: dir, ghBin: ghBin, out: out, err: errOut}
}

// Repository returns the owner/name identifier for the current repository.
func (c *Client) Repository(ctx context.Context) (string, error) {
	output, err := c.output(ctx,
		"repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner")
	if err != nil {
		return "", fmt.Errorf("resolving GitHub repository: %w", err)
	}
	return output, nil
}

// StackVersion returns the installed gh-stack extension version.
func (c *Client) StackVersion(ctx context.Context) (string, error) {
	output, err := c.output(ctx, "stack", "--version")
	if err != nil {
		return "", fmt.Errorf("checking gh-stack extension: %w", err)
	}
	return output, nil
}

// StacksAvailable verifies that the repository has the Stacked PRs preview.
func (c *Client) StacksAvailable(ctx context.Context, repository string) error {
	if _, err := c.output(ctx, "api", "repos/"+repository+"/stacks"); err != nil {
		return fmt.Errorf("checking Stacked PRs availability: %w", err)
	}
	return nil
}

// PullRequest returns the preferred open or merged pull request for a branch.
func (c *Client) PullRequest(
	ctx context.Context,
	repository string,
	branch string,
) (*state.PullRequest, error) {
	output, err := c.output(ctx,
		"pr", "list",
		"--repo", repository,
		"--head", branch,
		"--state", "all",
		"--limit", "100",
		"--json", "number,state,mergedAt,url,baseRefName,headRefName")
	if err != nil {
		return nil, fmt.Errorf("listing pull requests for %s: %w", branch, err)
	}

	var pullRequests []pullRequestWire
	if err := json.Unmarshal([]byte(output), &pullRequests); err != nil {
		return nil, fmt.Errorf("parsing pull requests for %s: %w", branch, err)
	}
	var fallback *pullRequestWire
	for index := range pullRequests {
		pullRequest := &pullRequests[index]
		if pullRequest.HeadRefName != branch {
			continue
		}
		if strings.EqualFold(pullRequest.State, "OPEN") {
			return pullRequestState(pullRequest), nil
		}
		if fallback == nil {
			fallback = pullRequest
		}
	}
	if fallback == nil {
		return nil, nil
	}
	return pullRequestState(fallback), nil
}

// Link creates or updates the remote Stack through gh stack link.
func (c *Client) Link(
	ctx context.Context,
	repository string,
	remote string,
	trunk string,
	branches []string,
) error {
	if len(branches) == 0 {
		return errors.New("stack has no active branches")
	}
	if len(branches) == 1 {
		pullRequest, err := c.PullRequest(ctx, repository, branches[0])
		if err != nil {
			return err
		}
		if pullRequest != nil && !pullRequest.Merged {
			return nil
		}
		if err := c.interactive(ctx,
			"pr", "create",
			"--repo", repository,
			"--base", trunk,
			"--head", branches[0],
			"--fill"); err != nil {
			return fmt.Errorf("creating pull request for %s: %w", branches[0], err)
		}
		return nil
	}

	args := []string{
		"stack", "link",
		"--base", trunk,
		"--remote", remote,
	}
	args = append(args, branches...)
	if err := c.interactive(ctx, args...); err != nil {
		return fmt.Errorf("linking GitHub stack: %w", err)
	}
	return nil
}

// CommandString formats a GitHub CLI invocation for dry-run output.
func CommandString(args ...string) string {
	quoted := make([]string, 0, len(args)+1)
	quoted = append(quoted, "gh")
	for _, arg := range args {
		quoted = append(quoted, strconv.Quote(arg))
	}
	return strings.Join(quoted, " ")
}

func pullRequestState(pullRequest *pullRequestWire) *state.PullRequest {
	return &state.PullRequest{
		Number: pullRequest.Number,
		URL:    pullRequest.URL,
		Base:   pullRequest.BaseRefName,
		State:  strings.ToLower(pullRequest.State),
		Merged: pullRequest.MergedAt != nil,
	}
}

func (c *Client) output(ctx context.Context, args ...string) (string, error) {
	command := exec.CommandContext(ctx, c.ghBin, args...)
	command.Dir = c.dir
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	command.Stdout = &stdout
	command.Stderr = &stderr
	if err := command.Run(); err != nil {
		message := strings.TrimSpace(stderr.String())
		if message == "" {
			message = err.Error()
		}
		return "", errors.New(message)
	}
	return strings.TrimSpace(stdout.String()), nil
}

func (c *Client) interactive(ctx context.Context, args ...string) error {
	command := exec.CommandContext(ctx, c.ghBin, args...)
	command.Dir = c.dir
	command.Stdin = os.Stdin
	command.Stdout = c.out
	var stderr bytes.Buffer
	command.Stderr = io.MultiWriter(c.err, &stderr)
	if err := command.Run(); err != nil {
		message := strings.TrimSpace(stderr.String())
		if message == "" {
			message = err.Error()
		}
		return fmt.Errorf("%s: %s", CommandString(args...), message)
	}
	return nil
}
