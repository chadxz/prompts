package github

import (
	"context"
	"fmt"
	"net/http"
	"net/url"
	"os/exec"
	"strings"

	"github.com/chadxz/prompts/apps/wt-stack/internal/state"
)

type pullRequestWire struct {
	Number   int     `json:"number"`
	State    string  `json:"state"`
	MergedAt *string `json:"merged_at"`
	URL      string  `json:"html_url"`
	Base     struct {
		Ref string `json:"ref"`
	} `json:"base"`
	Head struct {
		Ref string `json:"ref"`
	} `json:"head"`
}

type createPullRequestRequest struct {
	Title string `json:"title"`
	Head  string `json:"head"`
	Base  string `json:"base"`
	Body  string `json:"body,omitempty"`
	Draft bool   `json:"draft"`
}

// PullRequest returns the preferred open or merged pull request for a branch.
func (c *Client) PullRequest(
	ctx context.Context,
	repository Repository,
	branch string,
) (*state.PullRequest, error) {
	query := url.Values{
		"head":      {repository.Owner + ":" + branch},
		"state":     {"all"},
		"per_page":  {"100"},
		"sort":      {"created"},
		"direction": {"desc"},
	}
	path := "repos/" + repository.Slug() + "/pulls?" + query.Encode()
	var pullRequests []pullRequestWire
	if _, err := c.request(
		ctx,
		repository,
		http.MethodGet,
		path,
		nil,
		&pullRequests,
	); err != nil {
		return nil, fmt.Errorf("listing pull requests for %s: %w", branch, err)
	}

	var fallback *pullRequestWire
	for index := range pullRequests {
		pullRequest := &pullRequests[index]
		if pullRequest.Head.Ref != branch {
			continue
		}
		if strings.EqualFold(pullRequest.State, "open") {
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

func (c *Client) createPullRequest(
	ctx context.Context,
	repository Repository,
	branch string,
	base string,
) (*state.PullRequest, error) {
	title, body, err := c.commitMessage(ctx, branch)
	if err != nil {
		return nil, err
	}
	request := createPullRequestRequest{
		Title: title,
		Head:  branch,
		Base:  base,
		Body:  body,
		Draft: false,
	}
	var created pullRequestWire
	if _, err := c.request(
		ctx,
		repository,
		http.MethodPost,
		"repos/"+repository.Slug()+"/pulls",
		request,
		&created,
	); err != nil {
		return nil, err
	}
	return pullRequestState(&created), nil
}

func (c *Client) gitCommitMessage(
	ctx context.Context,
	branch string,
) (string, string, error) {
	// The configured Git binary is executed directly without a shell, and every
	// dynamic value is passed as a distinct argument.
	command := exec.CommandContext( //nolint:gosec // Git runs without a shell.
		ctx,
		c.gitBin,
		"-C",
		c.dir,
		"-c",
		"log.showSignature=false",
		"show",
		"-s",
		"--format=%s%x00%b",
		"refs/heads/"+branch,
	)
	output, err := command.Output()
	if err != nil {
		return "", "", fmt.Errorf(
			"reading commit message for branch %q: %w",
			branch,
			err,
		)
	}
	title, body, _ := strings.Cut(string(output), "\x00")
	title = strings.TrimSpace(title)
	if title == "" {
		return "", "", fmt.Errorf("branch %q has an empty commit title", branch)
	}
	return title, strings.TrimSpace(body), nil
}

func pullRequestState(pullRequest *pullRequestWire) *state.PullRequest {
	stateName := strings.ToLower(pullRequest.State)
	if pullRequest.MergedAt != nil {
		stateName = "merged"
	}
	return &state.PullRequest{
		Number: pullRequest.Number,
		URL:    pullRequest.URL,
		Base:   pullRequest.Base.Ref,
		State:  stateName,
		Merged: pullRequest.MergedAt != nil,
	}
}
