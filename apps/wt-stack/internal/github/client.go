package github

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	ghauth "github.com/cli/go-gh/v2/pkg/auth"
	ghconfig "github.com/cli/go-gh/v2/pkg/config"
	"github.com/zalando/go-keyring"
)

const defaultRequestTimeout = 30 * time.Second

type tokenProvider func(context.Context, string) (string, error)
type commitMessageProvider func(context.Context, string) (string, string, error)

// Option configures a GitHub API client.
type Option func(*Client)

// Client performs authenticated GitHub API operations.
type Client struct {
	dir           string
	gitBin        string
	httpClient    *http.Client
	tokenProvider tokenProvider
	commitMessage commitMessageProvider
	tokenMutex    sync.Mutex
	tokens        map[string]string
}

// NewClient creates a GitHub API client rooted in a repository worktree.
func NewClient(dir string, options ...Option) *Client {
	gitBin := os.Getenv("WT_STACK_GIT_BIN")
	if gitBin == "" {
		gitBin = "git"
	}
	client := &Client{
		dir:        dir,
		gitBin:     gitBin,
		httpClient: &http.Client{Timeout: defaultRequestTimeout},
		tokens:     make(map[string]string),
	}
	client.tokenProvider = tokenFromGitHubCLI
	client.commitMessage = client.gitCommitMessage
	for _, option := range options {
		option(client)
	}
	return client
}

func withCommitMessageProvider(provider commitMessageProvider) Option {
	return func(client *Client) {
		client.commitMessage = provider
	}
}

// WithHTTPClient replaces the default bounded HTTP client.
func WithHTTPClient(httpClient *http.Client) Option {
	return func(client *Client) {
		client.httpClient = httpClient
	}
}

// WithTokenProvider replaces GitHub CLI authentication token discovery.
func WithTokenProvider(provider func(context.Context, string) (string, error)) Option {
	return func(client *Client) {
		client.tokenProvider = provider
	}
}

// Authenticate verifies that authentication is available for a GitHub host.
func (c *Client) Authenticate(ctx context.Context, host string) error {
	if _, err := c.token(ctx, host); err != nil {
		return fmt.Errorf("authenticating to %s: %w", host, err)
	}
	return nil
}

func (c *Client) token(ctx context.Context, host string) (string, error) {
	c.tokenMutex.Lock()
	defer c.tokenMutex.Unlock()

	if token := c.tokens[host]; token != "" {
		return token, nil
	}
	token, err := c.tokenProvider(ctx, host)
	if err != nil {
		return "", err
	}
	token = strings.TrimSpace(token)
	if token == "" {
		return "", errors.New("authentication returned an empty token")
	}
	c.tokens[host] = token
	return token, nil
}

func (c *Client) invalidateToken(host string) {
	c.tokenMutex.Lock()
	defer c.tokenMutex.Unlock()
	delete(c.tokens, host)
}

func tokenFromGitHubCLI(
	ctx context.Context,
	host string,
) (string, error) {
	normalizedHost := ghauth.NormalizeHostname(host)
	if token, _ := ghauth.TokenFromEnvOrConfig(normalizedHost); token != "" {
		return token, nil
	}

	config, err := ghconfig.Read(nil)
	if err != nil {
		return "", fmt.Errorf("reading GitHub CLI configuration: %w", err)
	}
	user, userErr := config.Get([]string{"hosts", normalizedHost, "user"})
	var keyringErrors []error
	if userErr == nil && user != "" {
		if token, getErr := keyringToken(
			ctx,
			"gh:"+normalizedHost,
			user,
		); getErr == nil && strings.TrimSpace(token) != "" {
			return token, nil
		} else if getErr != nil && !errors.Is(getErr, keyring.ErrNotFound) {
			keyringErrors = append(keyringErrors, getErr)
		}
	}
	token, keyringErr := keyringToken(ctx, "gh:"+normalizedHost, "")
	if keyringErr == nil && strings.TrimSpace(token) != "" {
		return token, nil
	}
	if keyringErr != nil && !errors.Is(keyringErr, keyring.ErrNotFound) {
		keyringErrors = append(keyringErrors, keyringErr)
	}
	if len(keyringErrors) > 0 {
		return "", fmt.Errorf(
			"reading GitHub CLI keyring for %s: %w",
			normalizedHost,
			errors.Join(keyringErrors...),
		)
	}
	if userErr != nil {
		return "", fmt.Errorf(
			"no active GitHub CLI account is configured for %s",
			normalizedHost,
		)
	}
	return "", fmt.Errorf(
		"GitHub CLI has no usable credential for %s (active user %s)",
		normalizedHost,
		user,
	)
}

func keyringToken(
	ctx context.Context,
	service string,
	user string,
) (string, error) {
	type result struct {
		token string
		err   error
	}
	results := make(chan result, 1)
	go func() {
		token, err := keyring.Get(service, user)
		results <- result{token: token, err: err}
	}()
	select {
	case <-ctx.Done():
		return "", fmt.Errorf("reading GitHub CLI keyring: %w", ctx.Err())
	case found := <-results:
		return found.token, found.err
	}
}
