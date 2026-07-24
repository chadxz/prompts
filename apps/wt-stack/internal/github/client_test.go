package github

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestLinkCreatesAStackThroughHTTP(t *testing.T) {
	var stackRequest stackRequest
	server := newGitHubServer(t, func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		requireAuthorization(t, request)
		switch {
		case request.Method == http.MethodGet &&
			request.URL.Path == "/repos/example/repository/pulls":
			branch := strings.TrimPrefix(
				request.URL.Query().Get("head"),
				"example:",
			)
			number := map[string]int{"feature-one": 11, "feature-two": 12}[branch]
			writeJSON(t, writer, []any{
				pullRequestResponse(number, branch, expectedBase(branch)),
			})
		case request.Method == http.MethodGet &&
			request.URL.Path == "/repos/example/repository/stacks":
			writeJSON(t, writer, []any{})
		case request.Method == http.MethodPost &&
			request.URL.Path == "/repos/example/repository/stacks":
			readJSON(t, request, &stackRequest)
			writer.WriteHeader(http.StatusCreated)
		default:
			t.Fatalf("unexpected request: %s %s", request.Method, request.URL)
		}
	})
	defer server.Close()

	client := testClient(t, t.TempDir(), server)
	if err := client.Link(
		context.Background(),
		testRepository(server),
		"main",
		[]string{"feature-one", "feature-two"},
	); err != nil {
		t.Fatalf("link stack: %v", err)
	}
	if got, want := fmt.Sprint(stackRequest.PullRequests), "[11 12]"; got != want {
		t.Fatalf("pull requests = %s, want %s", got, want)
	}
}

func TestLinkAppendsToAnExistingStack(t *testing.T) {
	var added stackRequest
	server := newGitHubServer(t, func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		switch {
		case request.Method == http.MethodGet &&
			request.URL.Path == "/repos/example/repository/pulls":
			branch := strings.TrimPrefix(
				request.URL.Query().Get("head"),
				"example:",
			)
			number := map[string]int{"feature-one": 11, "feature-two": 12}[branch]
			writeJSON(t, writer, []any{
				pullRequestResponse(number, branch, expectedBase(branch)),
			})
		case request.Method == http.MethodGet &&
			request.URL.Path == "/repos/example/repository/stacks":
			writeJSON(t, writer, []any{map[string]any{
				"id":            100,
				"number":        13,
				"pull_requests": []any{map[string]any{"number": 11}},
			}})
		case request.Method == http.MethodPost &&
			request.URL.Path == "/repos/example/repository/stacks/13/add":
			readJSON(t, request, &added)
			writer.WriteHeader(http.StatusCreated)
		default:
			t.Fatalf("unexpected request: %s %s", request.Method, request.URL)
		}
	})
	defer server.Close()

	client := testClient(t, t.TempDir(), server)
	if err := client.Link(
		context.Background(),
		testRepository(server),
		"main",
		[]string{"feature-one", "feature-two"},
	); err != nil {
		t.Fatalf("append stack: %v", err)
	}
	if got, want := fmt.Sprint(added.PullRequests), "[12]"; got != want {
		t.Fatalf("added pull requests = %s, want %s", got, want)
	}
}

func TestLinkCreatesMissingPullRequestsAndRepairsBases(t *testing.T) {
	root := newCommitRepository(t)
	var created createPullRequestRequest
	var repaired struct {
		Base string `json:"base"`
	}
	var linked stackRequest
	server := newGitHubServer(t, func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		switch {
		case request.Method == http.MethodGet &&
			request.URL.Path == "/repos/example/repository/pulls":
			branch := strings.TrimPrefix(
				request.URL.Query().Get("head"),
				"example:",
			)
			if branch == "feature-one" {
				writeJSON(t, writer, []any{
					pullRequestResponse(11, branch, "wrong-base"),
				})
				return
			}
			writeJSON(t, writer, []any{})
		case request.Method == http.MethodGet &&
			request.URL.Path == "/repos/example/repository/stacks":
			writeJSON(t, writer, []any{})
		case request.Method == http.MethodPost &&
			request.URL.Path == "/repos/example/repository/pulls":
			readJSON(t, request, &created)
			writer.WriteHeader(http.StatusCreated)
			writeJSON(t, writer, pullRequestResponse(
				12,
				"feature-two",
				"feature-one",
			))
		case request.Method == http.MethodPatch &&
			request.URL.Path == "/repos/example/repository/pulls/11":
			readJSON(t, request, &repaired)
			writeJSON(t, writer, pullRequestResponse(
				11,
				"feature-one",
				"main",
			))
		case request.Method == http.MethodPost &&
			request.URL.Path == "/repos/example/repository/stacks":
			readJSON(t, request, &linked)
			writer.WriteHeader(http.StatusCreated)
		default:
			t.Fatalf("unexpected request: %s %s", request.Method, request.URL)
		}
	})
	defer server.Close()

	client := testClient(t, root, server)
	if err := client.Link(
		context.Background(),
		testRepository(server),
		"main",
		[]string{"feature-one", "feature-two"},
	); err != nil {
		t.Fatalf("link stack: %v", err)
	}
	if created.Title != "Feature two" ||
		created.Head != "feature-two" ||
		created.Base != "feature-one" ||
		created.Draft {
		t.Fatalf("unexpected pull request create body: %#v", created)
	}
	if repaired.Base != "main" {
		t.Fatalf("repaired base = %q, want main", repaired.Base)
	}
	if got, want := fmt.Sprint(linked.PullRequests), "[11 12]"; got != want {
		t.Fatalf("linked pull requests = %s, want %s", got, want)
	}
}

func TestLinkChecksPreviewBeforeCreatingPullRequests(t *testing.T) {
	var writes int
	server := newGitHubServer(t, func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		if request.Method != http.MethodGet {
			writes++
		}
		switch request.URL.Path {
		case "/repos/example/repository/pulls":
			writeJSON(t, writer, []any{})
		case "/repos/example/repository/stacks":
			writer.WriteHeader(http.StatusNotFound)
			writeJSON(t, writer, map[string]any{"message": "Not Found"})
		default:
			t.Fatalf("unexpected request: %s %s", request.Method, request.URL)
		}
	})
	defer server.Close()

	client := testClient(t, t.TempDir(), server)
	err := client.Link(
		context.Background(),
		testRepository(server),
		"main",
		[]string{"feature-one", "feature-two"},
	)
	if err == nil || !strings.Contains(err.Error(), "HTTP 404") {
		t.Fatalf("Link() error = %v, want preview 404", err)
	}
	if writes != 0 {
		t.Fatalf("made %d writes before checking preview", writes)
	}
}

func TestLinkReplacesClosedUnmergedPullRequest(t *testing.T) {
	root := newCommitRepository(t)
	var created createPullRequestRequest
	server := newGitHubServer(t, func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		switch {
		case request.Method == http.MethodGet &&
			request.URL.Path == "/repos/example/repository/pulls":
			branch := strings.TrimPrefix(
				request.URL.Query().Get("head"),
				"example:",
			)
			if branch == "feature-one" {
				writeJSON(t, writer, []any{
					pullRequestResponse(11, branch, "main"),
				})
				return
			}
			closed := pullRequestResponse(12, branch, "feature-one")
			closed["state"] = "closed"
			writeJSON(t, writer, []any{closed})
		case request.Method == http.MethodGet &&
			request.URL.Path == "/repos/example/repository/stacks":
			writeJSON(t, writer, []any{})
		case request.Method == http.MethodPost &&
			request.URL.Path == "/repos/example/repository/pulls":
			readJSON(t, request, &created)
			writer.WriteHeader(http.StatusCreated)
			writeJSON(t, writer, pullRequestResponse(
				13,
				"feature-two",
				"feature-one",
			))
		case request.Method == http.MethodPost &&
			request.URL.Path == "/repos/example/repository/stacks":
			writer.WriteHeader(http.StatusCreated)
		default:
			t.Fatalf("unexpected request: %s %s", request.Method, request.URL)
		}
	})
	defer server.Close()

	client := testClient(t, root, server)
	if err := client.Link(
		context.Background(),
		testRepository(server),
		"main",
		[]string{"feature-one", "feature-two"},
	); err != nil {
		t.Fatalf("replace closed pull request: %v", err)
	}
	if created.Head != "feature-two" || created.Base != "feature-one" {
		t.Fatalf("unexpected replacement pull request: %#v", created)
	}
}

func TestLinkPreservesMergedStackMembers(t *testing.T) {
	server := newGitHubServer(t, func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		switch request.URL.Path {
		case "/repos/example/repository/pulls":
			branch := strings.TrimPrefix(
				request.URL.Query().Get("head"),
				"example:",
			)
			response := pullRequestResponse(
				map[string]int{"merged-feature": 9, "active-feature": 10}[branch],
				branch,
				"main",
			)
			if branch == "merged-feature" {
				response["state"] = "closed"
				response["merged_at"] = "2026-07-24T12:00:00Z"
			}
			writeJSON(t, writer, []any{response})
		case "/repos/example/repository/stacks":
			writeJSON(t, writer, []any{map[string]any{
				"id":     100,
				"number": 11,
				"pull_requests": []any{
					map[string]any{"number": 9},
					map[string]any{"number": 10},
				},
			}})
		default:
			t.Fatalf("unexpected request: %s %s", request.Method, request.URL)
		}
	})
	defer server.Close()

	client := testClient(t, t.TempDir(), server)
	if err := client.Link(
		context.Background(),
		testRepository(server),
		"main",
		[]string{"merged-feature", "active-feature"},
	); err != nil {
		t.Fatalf("link stack with merged member: %v", err)
	}
}

func TestLinkOmitsMergedMembersWhenCreatingAStack(t *testing.T) {
	var linked stackRequest
	server := newGitHubServer(t, func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		switch {
		case request.Method == http.MethodGet &&
			request.URL.Path == "/repos/example/repository/pulls":
			branch := strings.TrimPrefix(
				request.URL.Query().Get("head"),
				"example:",
			)
			response := pullRequestResponse(
				map[string]int{"merged-feature": 9, "active-feature": 10}[branch],
				branch,
				"main",
			)
			if branch == "merged-feature" {
				response["state"] = "closed"
				response["merged_at"] = "2026-07-24T12:00:00Z"
			}
			writeJSON(t, writer, []any{response})
		case request.Method == http.MethodGet &&
			request.URL.Path == "/repos/example/repository/stacks":
			writeJSON(t, writer, []any{})
		case request.Method == http.MethodPost &&
			request.URL.Path == "/repos/example/repository/stacks":
			readJSON(t, request, &linked)
			writer.WriteHeader(http.StatusCreated)
		default:
			t.Fatalf("unexpected request: %s %s", request.Method, request.URL)
		}
	})
	defer server.Close()

	client := testClient(t, t.TempDir(), server)
	if err := client.Link(
		context.Background(),
		testRepository(server),
		"main",
		[]string{"merged-feature", "active-feature"},
	); err != nil {
		t.Fatalf("link stack with merged member: %v", err)
	}
	if got, want := fmt.Sprint(linked.PullRequests), "[10]"; got != want {
		t.Fatalf("linked pull requests = %s, want %s", got, want)
	}
}

func TestLinkAcceptsExistingStackAfterBottomPullRequestMerged(t *testing.T) {
	var writes int
	server := newGitHubServer(t, func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		if request.Method != http.MethodGet {
			writes++
		}
		switch request.URL.Path {
		case "/repos/example/repository/pulls":
			branch := strings.TrimPrefix(
				request.URL.Query().Get("head"),
				"example:",
			)
			response := pullRequestResponse(
				map[string]int{"merged-feature": 9, "active-feature": 10}[branch],
				branch,
				"main",
			)
			if branch == "merged-feature" {
				response["state"] = "closed"
				response["merged_at"] = "2026-07-24T12:00:00Z"
			}
			writeJSON(t, writer, []any{response})
		case "/repos/example/repository/stacks":
			writeJSON(t, writer, []any{map[string]any{
				"id":            100,
				"number":        11,
				"pull_requests": []any{map[string]any{"number": 10}},
			}})
		default:
			t.Fatalf("unexpected request: %s %s", request.Method, request.URL)
		}
	})
	defer server.Close()

	client := testClient(t, t.TempDir(), server)
	if err := client.Link(
		context.Background(),
		testRepository(server),
		"main",
		[]string{"merged-feature", "active-feature"},
	); err != nil {
		t.Fatalf("link stack after bottom merge: %v", err)
	}
	if writes != 0 {
		t.Fatalf("made %d unexpected writes", writes)
	}
}

func TestLinkFindsExistingStackOnLaterPage(t *testing.T) {
	var added stackRequest
	server := newGitHubServer(t, func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		switch {
		case request.Method == http.MethodGet &&
			request.URL.Path == "/repos/example/repository/pulls":
			branch := strings.TrimPrefix(
				request.URL.Query().Get("head"),
				"example:",
			)
			number := map[string]int{"feature-one": 11, "feature-two": 12}[branch]
			writeJSON(t, writer, []any{
				pullRequestResponse(number, branch, expectedBase(branch)),
			})
		case request.Method == http.MethodGet &&
			request.URL.Path == "/repos/example/repository/stacks" &&
			request.URL.Query().Get("page") == "":
			writer.Header().Set(
				"Link",
				"<"+serverURL(request)+
					"/repos/example/repository/stacks?page=2>; rel=\"next\"",
			)
			writeJSON(t, writer, []any{})
		case request.Method == http.MethodGet &&
			request.URL.Path == "/repos/example/repository/stacks":
			writeJSON(t, writer, []any{map[string]any{
				"id":            100,
				"number":        13,
				"pull_requests": []any{map[string]any{"number": 11}},
			}})
		case request.Method == http.MethodPost &&
			request.URL.Path == "/repos/example/repository/stacks/13/add":
			readJSON(t, request, &added)
			writer.WriteHeader(http.StatusCreated)
		default:
			t.Fatalf("unexpected request: %s %s", request.Method, request.URL)
		}
	})
	defer server.Close()

	client := testClient(t, t.TempDir(), server)
	if err := client.Link(
		context.Background(),
		testRepository(server),
		"main",
		[]string{"feature-one", "feature-two"},
	); err != nil {
		t.Fatalf("link paginated stack: %v", err)
	}
	if got, want := fmt.Sprint(added.PullRequests), "[12]"; got != want {
		t.Fatalf("added pull requests = %s, want %s", got, want)
	}
}

func TestPullRequestPrefersOpenMatch(t *testing.T) {
	server := newGitHubServer(t, func(
		writer http.ResponseWriter,
		_ *http.Request,
	) {
		merged := pullRequestResponse(8, "feature", "main")
		merged["state"] = "closed"
		merged["merged_at"] = "2026-07-20T00:00:00Z"
		writeJSON(t, writer, []any{
			merged,
			pullRequestResponse(9, "feature", "main"),
		})
	})
	defer server.Close()

	client := testClient(t, t.TempDir(), server)
	pullRequest, err := client.PullRequest(
		context.Background(),
		testRepository(server),
		"feature",
	)
	if err != nil {
		t.Fatalf("read pull request: %v", err)
	}
	if pullRequest == nil ||
		pullRequest.Number != 9 ||
		pullRequest.Merged {
		t.Fatalf("unexpected pull request: %#v", pullRequest)
	}
}

func TestPullRequestReportsMergedState(t *testing.T) {
	mergedAt := "2026-07-24T12:00:00Z"
	wire := pullRequestWire{
		Number:   9,
		State:    "closed",
		MergedAt: &mergedAt,
	}
	pullRequest := pullRequestState(&wire)
	if pullRequest.State != "merged" || !pullRequest.Merged {
		t.Fatalf("unexpected merged pull request: %#v", pullRequest)
	}
}

func TestRequestRefreshesAuthenticationAfterUnauthorized(t *testing.T) {
	var mutex sync.Mutex
	tokens := []string{"expired", "current"}
	tokenCalls := 0
	server := newGitHubServer(t, func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		if request.Header.Get("Authorization") == "Bearer expired" {
			writer.WriteHeader(http.StatusUnauthorized)
			return
		}
		writeJSON(t, writer, []any{})
	})
	defer server.Close()

	client := NewClient(
		t.TempDir(),
		WithHTTPClient(server.Client()),
		WithTokenProvider(func(
			_ context.Context,
			_ string,
		) (string, error) {
			mutex.Lock()
			defer mutex.Unlock()
			token := tokens[tokenCalls]
			tokenCalls++
			return token, nil
		}),
	)
	if err := client.StacksAvailable(
		context.Background(),
		testRepository(server),
	); err != nil {
		t.Fatalf("check Stacks availability: %v", err)
	}
	if tokenCalls != 2 {
		t.Fatalf("token provider calls = %d, want 2", tokenCalls)
	}
}

func TestRequestRetriesRateLimitWithoutRefreshingAuthentication(t *testing.T) {
	var requests int
	var tokenCalls int
	server := newGitHubServer(t, func(
		writer http.ResponseWriter,
		_ *http.Request,
	) {
		requests++
		if requests == 1 {
			writer.Header().Set("Retry-After", "0")
			writer.WriteHeader(http.StatusForbidden)
			return
		}
		writeJSON(t, writer, []any{})
	})
	defer server.Close()

	client := NewClient(
		t.TempDir(),
		WithHTTPClient(server.Client()),
		WithTokenProvider(func(
			_ context.Context,
			_ string,
		) (string, error) {
			tokenCalls++
			return "current", nil
		}),
	)
	if err := client.StacksAvailable(
		context.Background(),
		testRepository(server),
	); err != nil {
		t.Fatalf("check Stacks availability: %v", err)
	}
	if requests != 2 {
		t.Fatalf("requests = %d, want 2", requests)
	}
	if tokenCalls != 1 {
		t.Fatalf("token provider calls = %d, want 1", tokenCalls)
	}
}

func TestRetryDelayHonorsGitHubHeaders(t *testing.T) {
	now := time.Date(2026, 7, 24, 12, 0, 0, 0, time.UTC)
	tests := []struct {
		name    string
		headers http.Header
		want    time.Duration
	}{
		{
			name:    "retry after seconds",
			headers: http.Header{"Retry-After": []string{"45"}},
			want:    45 * time.Second,
		},
		{
			name: "retry after date",
			headers: http.Header{
				"Retry-After": []string{
					now.Add(30 * time.Second).Format(http.TimeFormat),
				},
			},
			want: 30 * time.Second,
		},
		{
			name: "rate limit reset",
			headers: http.Header{
				"X-Ratelimit-Reset": []string{
					strconv.FormatInt(now.Add(20*time.Second).Unix(), 10),
				},
			},
			want: 20 * time.Second,
		},
		{
			name:    "maximum delay",
			headers: http.Header{"Retry-After": []string{"120"}},
			want:    maxRetryDelay,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if got := retryDelay(now, 0, test.headers); got != test.want {
				t.Fatalf("delay = %s, want %s", got, test.want)
			}
		})
	}
}

func TestAPIErrorIncludesValidationDetails(t *testing.T) {
	response := []byte(`{
		"message": "Validation Failed",
		"errors": [
			"No commits between main and feature",
			{"resource": "PullRequest", "field": "head", "code": "invalid"}
		]
	}`)
	err := decodeAPIError(
		http.StatusUnprocessableEntity,
		"repos/example/repository/pulls",
		response,
	)
	message := err.Error()
	for _, wanted := range []string{
		"repos/example/repository/pulls",
		"No commits between main and feature",
		"PullRequest.head invalid",
	} {
		if !strings.Contains(message, wanted) {
			t.Fatalf("error %q does not contain %q", message, wanted)
		}
	}
}

func TestRequestRejectsMismatchedAPIHostBeforeReadingToken(t *testing.T) {
	var tokenCalls int
	client := NewClient(
		t.TempDir(),
		WithTokenProvider(func(
			_ context.Context,
			_ string,
		) (string, error) {
			tokenCalls++
			return "secret", nil
		}),
	)
	err := client.StacksAvailable(context.Background(), Repository{
		Host:   "github.com",
		Owner:  "example",
		Name:   "repository",
		APIURL: "https://attacker.example",
	})
	if err == nil || !strings.Contains(err.Error(), "refusing to send") {
		t.Fatalf("StacksAvailable() error = %v, want host rejection", err)
	}
	if tokenCalls != 0 {
		t.Fatalf("token provider calls = %d, want 0", tokenCalls)
	}
	err = client.StacksAvailable(context.Background(), Repository{
		Host:   "github.com",
		Owner:  "example",
		Name:   "repository",
		APIURL: "http://api.github.com",
	})
	if err == nil || !strings.Contains(err.Error(), "over \"http\"") {
		t.Fatalf("StacksAvailable() error = %v, want scheme rejection", err)
	}
	if tokenCalls != 0 {
		t.Fatalf("token provider calls after scheme check = %d, want 0", tokenCalls)
	}
}

func TestTokenFromGitHubCLIReadsExistingConfiguration(t *testing.T) {
	configDirectory := t.TempDir()
	hosts := `github.com:
    user: example
    oauth_token: configured-token
    git_protocol: ssh
`
	if err := os.WriteFile(
		filepath.Join(configDirectory, "hosts.yml"),
		[]byte(hosts),
		0o600,
	); err != nil {
		t.Fatalf("write hosts config: %v", err)
	}
	t.Setenv("GH_CONFIG_DIR", configDirectory)
	t.Setenv("GH_TOKEN", "")
	t.Setenv("GITHUB_TOKEN", "")

	token, err := tokenFromGitHubCLI(context.Background(), "github.com")
	if err != nil {
		t.Fatalf("read configured token: %v", err)
	}
	if token != "configured-token" {
		t.Fatalf("token = %q, want configured-token", token)
	}
}

func TestParseRepositoryURL(t *testing.T) {
	tests := []struct {
		name      string
		remoteURL string
		want      Repository
	}{
		{
			name:      "HTTPS",
			remoteURL: "https://github.com/example/repository.git",
			want: Repository{
				Host:   "github.com",
				Owner:  "example",
				Name:   "repository",
				APIURL: "https://api.github.com",
			},
		},
		{
			name:      "SSH",
			remoteURL: "git@github.com:example/repository.git",
			want: Repository{
				Host:   "github.com",
				Owner:  "example",
				Name:   "repository",
				APIURL: "https://api.github.com",
			},
		},
		{
			name:      "GitHub Enterprise",
			remoteURL: "ssh://git@git.example.com/example/repository.git",
			want: Repository{
				Host:   "git.example.com",
				Owner:  "example",
				Name:   "repository",
				APIURL: "https://git.example.com/api/v3",
			},
		},
		{
			name:      "GitHub SSH fallback",
			remoteURL: "ssh://git@ssh.github.com:443/example/repository.git",
			want: Repository{
				Host:   "github.com",
				Owner:  "example",
				Name:   "repository",
				APIURL: "https://api.github.com",
			},
		},
		{
			name:      "GHE tenancy",
			remoteURL: "git@acme.ghe.com:example/repository.git",
			want: Repository{
				Host:   "acme.ghe.com",
				Owner:  "example",
				Name:   "repository",
				APIURL: "https://api.acme.ghe.com",
			},
		},
		{
			name:      "enterprise port",
			remoteURL: "ssh://git@git.example.com:8443/example/repository.git",
			want: Repository{
				Host:   "git.example.com",
				Owner:  "example",
				Name:   "repository",
				APIURL: "https://git.example.com/api/v3",
			},
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			got, err := parseRepositoryURL(test.remoteURL)
			if err != nil {
				t.Fatalf("parse repository URL: %v", err)
			}
			if got != test.want {
				t.Fatalf("repository = %#v, want %#v", got, test.want)
			}
		})
	}
}

func TestParseRepositoryURLRejectsLocalPathWithoutEchoingCredentials(
	t *testing.T,
) {
	if _, err := parseRepositoryURL(`C:\repos\repository`); err == nil {
		t.Fatal("Windows local path was accepted")
	}
	_, err := parseRepositoryURL(
		"https://x-access-token:secret@github.com/example",
	)
	if err == nil {
		t.Fatal("malformed credential-bearing URL was accepted")
	}
	if strings.Contains(err.Error(), "secret") {
		t.Fatalf("error exposes URL credentials: %v", err)
	}
}

func TestRepositoryRejectsUnknownRemoteHost(t *testing.T) {
	root := t.TempDir()
	runGit(t, root, "init", "--initial-branch=main")
	runGit(
		t,
		root,
		"remote",
		"add",
		"origin",
		"https://attacker.example/example/repository.git",
	)
	client := NewClient(root)
	_, err := client.Repository(context.Background(), "origin")
	if err == nil || !strings.Contains(err.Error(), "not configured") {
		t.Fatalf("Repository() error = %v, want unknown-host rejection", err)
	}
}

func TestRepositoryExpandsInsteadOfRemote(t *testing.T) {
	root := t.TempDir()
	runGit(t, root, "init", "--initial-branch=main")
	runGit(
		t,
		root,
		"config",
		`url.git@github.com:.insteadOf`,
		"gh:",
	)
	runGit(t, root, "remote", "add", "origin", "gh:example/repository.git")
	client := NewClient(root)
	repository, err := client.Repository(context.Background(), "origin")
	if err != nil {
		t.Fatalf("resolve rewritten remote: %v", err)
	}
	if repository.Host != "github.com" ||
		repository.Slug() != "example/repository" {
		t.Fatalf("unexpected repository: %#v", repository)
	}
}

func testClient(
	t *testing.T,
	dir string,
	server *httptest.Server,
) *Client {
	t.Helper()
	return NewClient(
		dir,
		WithHTTPClient(server.Client()),
		WithTokenProvider(func(
			_ context.Context,
			_ string,
		) (string, error) {
			return "test-token", nil
		}),
	)
}

func testRepository(server *httptest.Server) Repository {
	serverURL, err := url.Parse(server.URL)
	if err != nil {
		panic(err)
	}
	return Repository{
		Host:   serverURL.Hostname(),
		Owner:  "example",
		Name:   "repository",
		APIURL: server.URL,
	}
}

func newGitHubServer(
	t *testing.T,
	handler func(http.ResponseWriter, *http.Request),
) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(handler))
}

func serverURL(request *http.Request) string {
	return "http://" + request.Host
}

func requireAuthorization(t *testing.T, request *http.Request) {
	t.Helper()
	if got, want := request.Header.Get("Authorization"),
		"Bearer test-token"; got != want {
		t.Fatalf("authorization = %q, want %q", got, want)
	}
}

func pullRequestResponse(
	number int,
	head string,
	base string,
) map[string]any {
	return map[string]any{
		"number":    number,
		"state":     "open",
		"merged_at": nil,
		"html_url":  fmt.Sprintf("https://example.test/pull/%d", number),
		"base":      map[string]any{"ref": base},
		"head":      map[string]any{"ref": head},
	}
}

func expectedBase(branch string) string {
	if branch == "feature-one" {
		return "main"
	}
	return "feature-one"
}

func readJSON(t *testing.T, request *http.Request, destination any) {
	t.Helper()
	defer func() {
		_ = request.Body.Close()
	}()
	if err := json.NewDecoder(request.Body).Decode(destination); err != nil {
		t.Fatalf("decode request body: %v", err)
	}
}

func writeJSON(t *testing.T, writer http.ResponseWriter, value any) {
	t.Helper()
	writer.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(writer).Encode(value); err != nil {
		t.Fatalf("encode response: %v", err)
	}
}

func newCommitRepository(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	runGit(t, root, "init", "--initial-branch=main")
	runGit(t, root, "config", "user.email", "wt-stack@example.test")
	runGit(t, root, "config", "user.name", "wt-stack")
	file := filepath.Join(root, "file.txt")
	if err := os.WriteFile(file, []byte("content\n"), 0o600); err != nil {
		t.Fatalf("write fixture: %v", err)
	}
	runGit(t, root, "add", "file.txt")
	runGit(t, root, "commit", "-m", "Feature two", "-m", "Pull request body")
	runGit(t, root, "branch", "feature-two")
	return root
}

func runGit(t *testing.T, dir string, arguments ...string) {
	t.Helper()
	command := exec.Command("git", arguments...)
	command.Dir = dir
	command.Stdout = io.Discard
	command.Stderr = io.Discard
	if err := command.Run(); err != nil {
		t.Fatalf("git %s: %v", strings.Join(arguments, " "), err)
	}
}
