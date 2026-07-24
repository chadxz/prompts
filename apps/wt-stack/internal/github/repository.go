package github

import (
	"context"
	"fmt"
	"net/url"
	"os/exec"
	"strings"
	"unicode"

	ghauth "github.com/cli/go-gh/v2/pkg/auth"
	"github.com/cli/go-gh/v2/pkg/ssh"
)

// Repository identifies a GitHub repository and its API endpoint.
type Repository struct {
	Host   string `json:"host"`
	Owner  string `json:"owner"`
	Name   string `json:"name"`
	APIURL string `json:"apiUrl"`
}

// Slug returns the owner/name repository identifier.
func (r Repository) Slug() string {
	return r.Owner + "/" + r.Name
}

// Repository resolves a GitHub repository from a configured Git remote.
func (c *Client) Repository(
	ctx context.Context,
	remote string,
) (Repository, error) {
	if remote == "" {
		remote = "origin"
	}
	command := exec.CommandContext(
		ctx,
		c.gitBin,
		"-C",
		c.dir,
		"ls-remote",
		"--get-url",
		remote,
	)
	output, err := command.CombinedOutput()
	if err != nil {
		return Repository{}, fmt.Errorf(
			"resolving Git remote %q: %s",
			remote,
			strings.TrimSpace(string(output)),
		)
	}
	remoteURL := strings.TrimSpace(string(output))
	parsedURL, err := parseRemoteURL(remoteURL)
	if err != nil {
		return Repository{}, fmt.Errorf(
			"resolving GitHub repository from remote %q: %w",
			remote,
			err,
		)
	}
	parsedURL = ssh.NewTranslator().Translate(parsedURL)
	repository, err := repositoryFromURL(parsedURL)
	if err != nil {
		return Repository{}, fmt.Errorf(
			"resolving GitHub repository from remote %q: %w",
			remote,
			err,
		)
	}
	if err := validateKnownGitHubHost(repository.Host); err != nil {
		return Repository{}, fmt.Errorf(
			"resolving GitHub repository from remote %q: %w",
			remote,
			err,
		)
	}
	return repository, nil
}

func parseRepositoryURL(remoteURL string) (Repository, error) {
	parsedURL, err := parseRemoteURL(remoteURL)
	if err != nil {
		return Repository{}, err
	}
	return repositoryFromURL(parsedURL)
}

func parseRemoteURL(remoteURL string) (*url.URL, error) {
	if isWindowsLocalPath(remoteURL) {
		return nil, fmt.Errorf("remote is a local path")
	}
	if strings.Contains(remoteURL, "://") {
		parsed, err := url.Parse(remoteURL)
		if err != nil {
			return nil, fmt.Errorf("parsing remote URL: %w", err)
		}
		if parsed.Hostname() == "" {
			return nil, fmt.Errorf("remote URL has no host")
		}
		return parsed, nil
	}

	prefix, path, found := strings.Cut(remoteURL, ":")
	if !found || strings.HasPrefix(prefix, "/") {
		return nil, fmt.Errorf("remote is not a GitHub URL")
	}
	parsed, err := url.Parse("ssh://" + prefix + "/" + path)
	if err != nil {
		return nil, fmt.Errorf("parsing SSH remote URL: %w", err)
	}
	if parsed.Hostname() == "" {
		return nil, fmt.Errorf("remote URL has no host")
	}
	return parsed, nil
}

func repositoryFromURL(remoteURL *url.URL) (Repository, error) {
	host := ghauth.NormalizeHostname(remoteURL.Hostname())
	parts := strings.Split(strings.Trim(remoteURL.Path, "/"), "/")
	if host == "" || len(parts) != 2 {
		return Repository{}, fmt.Errorf(
			"remote URL does not identify owner/repository",
		)
	}
	name := strings.TrimSuffix(parts[1], ".git")
	if parts[0] == "" || name == "" {
		return Repository{}, fmt.Errorf(
			"remote URL does not identify owner/repository",
		)
	}

	return Repository{
		Host:   host,
		Owner:  parts[0],
		Name:   name,
		APIURL: apiURLForHost(host),
	}, nil
}

func apiURLForHost(host string) string {
	normalizedHost := ghauth.NormalizeHostname(host)
	if normalizedHost == "github.localhost" {
		return "http://api.github.localhost"
	}
	if ghauth.IsEnterprise(normalizedHost) {
		return "https://" + normalizedHost + "/api/v3"
	}
	return "https://api." + normalizedHost
}

func validateKnownGitHubHost(host string) error {
	normalizedHost := ghauth.NormalizeHostname(host)
	if normalizedHost == "github.com" {
		return nil
	}
	for _, knownHost := range ghauth.KnownHosts() {
		if ghauth.NormalizeHostname(knownHost) == normalizedHost {
			return nil
		}
	}
	return fmt.Errorf(
		"host %q is not configured in GitHub CLI authentication",
		normalizedHost,
	)
}

func isWindowsLocalPath(value string) bool {
	if len(value) < 3 || value[1] != ':' {
		return false
	}
	return unicode.IsLetter(rune(value[0])) &&
		(value[2] == '\\' || value[2] == '/')
}
