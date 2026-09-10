package github

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"testing"

	"github.com/chadxz/prompts/apps/wt-stack/internal/state"
)

func TestAsyncMergeHTTPResults(t *testing.T) {
	for _, test := range []struct {
		name     string
		code     int
		body     string
		want     string
		existing bool
		wantErr  bool
	}{
		{"pending", 202, `{"status":"pending","details":{"uuid":"request-1","expected_head_sha":"abc"}}`, "pending", false, false},
		{"merged", 200, `{"status":"merged","details":{"message":"merged"}}`, "merged", false, false},
		{"queued", 200, `{"status":"enqueued","details":{}}`, "enqueued", false, false},
		{"failed", 400, `{"status":"failed","details":{"message":"draft"}}`, "failed", false, false},
		{"existing", 409, `{"status":"pending","details":{"uuid":"old-request","expected_head_sha":"different"}}`, "pending", true, false},
		{"unsupported", 404, `{"message":"not found"}`, "", false, true},
		{"unknown", 200, `{"status":"unexpected"}`, "", false, true},
		{"empty uuid", 202, `{"status":"pending"}`, "", false, true},
		{"changed head", 202, `{"status":"pending","details":{"uuid":"request-1","expected_head_sha":"changed"}}`, "pending", false, true},
		{"invalid json", 200, `{`, "", false, true},
		{"wrong conflict", 409, `{"status":"merged"}`, "", false, true},
		{"wrong rejection", 400, `{"status":"enqueued"}`, "", false, true},
	} {
		t.Run(test.name, func(t *testing.T) {
			calls := 0
			server := newGitHubServer(t, func(w http.ResponseWriter, req *http.Request) {
				calls++
				requireAuthorization(t, req)
				if req.Method != http.MethodPut || req.URL.Path != "/repos/example/repository/pulls/42/merge-async" {
					t.Errorf("unexpected request: %s %s", req.Method, req.URL)
				}
				var body map[string]string
				readJSON(t, req, &body)
				if body["sha"] != "abc" || body["merge_action"] != "default" || body["merge_method"] != "squash" {
					t.Errorf("request body: %#v", body)
				}
				w.WriteHeader(test.code)
				_, _ = w.Write([]byte(test.body))
			})
			defer server.Close()
			client := testClient(t, t.TempDir(), server)
			result, err := client.StartMerge(context.Background(), testRepository(server), 42, "abc", "squash")
			if (err != nil) != test.wantErr {
				t.Fatalf("error = %v", err)
			}
			if test.want != "" && (result == nil || result.Status != test.want || result.Existing != test.existing) {
				t.Fatalf("result = %#v", result)
			}
			if calls != 1 {
				t.Fatalf("mutation attempted %d times", calls)
			}
		})
	}
}

func TestPollMergeUsesOnlyGET(t *testing.T) {
	for _, value := range []string{"pending", "merged", "enqueued", "failed"} {
		t.Run(value, func(t *testing.T) {
			server := newGitHubServer(t, func(w http.ResponseWriter, req *http.Request) {
				if req.Method != http.MethodGet || !strings.HasSuffix(req.URL.Path, "/42/merge-async/request-1") {
					t.Errorf("unexpected request: %s %s", req.Method, req.URL)
				}
				writeJSON(t, w, map[string]any{"status": value, "details": map[string]string{"uuid": "request-1", "message": "result"}})
			})
			defer server.Close()
			client := testClient(t, t.TempDir(), server)
			result, err := client.PollMerge(context.Background(), testRepository(server), 42, "request-1")
			if err != nil || result.Status != value || result.UUID != "request-1" {
				t.Fatalf("result = %#v, %v", result, err)
			}
			if _, err := client.PollMerge(context.Background(), testRepository(server), 42, "../other"); err == nil {
				t.Fatal("invalid UUID accepted")
			}
			if _, err := client.StartMerge(context.Background(), testRepository(server), 0, "", ""); err == nil {
				t.Fatal("missing head accepted")
			}
			if _, err := client.StartMerge(context.Background(), testRepository(server), 42, "abc", "invalid"); err == nil {
				t.Fatal("invalid method accepted")
			}
		})
	}
}

func TestMergeScopeRejectsUnexpectedMembers(t *testing.T) {
	for _, test := range []struct {
		name    string
		numbers []int
		members []state.PullRequest
		wantErr bool
	}{
		{"prefix", []int{1, 2, 3}, []state.PullRequest{{Number: 1}, {Number: 2}}, false},
		{"unknown parent", []int{9, 1, 2}, []state.PullRequest{{Number: 1}, {Number: 2}}, true},
		{"reordered", []int{2, 1, 3}, []state.PullRequest{{Number: 1}, {Number: 2}, {Number: 3}}, true},
		{"retained merged", []int{1, 2}, []state.PullRequest{{Number: 1, Merged: true}, {Number: 2}}, false},
		{"omitted merged", []int{2}, []state.PullRequest{{Number: 1, Merged: true}, {Number: 2}}, false},
		{"missing stack", nil, []state.PullRequest{{Number: 1}, {Number: 2}}, true},
		{"single unstacked", nil, []state.PullRequest{{Number: 1}}, false},
		{"no selection", nil, nil, true},
	} {
		t.Run(test.name, func(t *testing.T) {
			server := newGitHubServer(t, func(w http.ResponseWriter, req *http.Request) {
				if req.Method != http.MethodGet || !strings.HasSuffix(req.URL.Path, "/stacks") {
					t.Errorf("unexpected request: %s", req.URL)
				}
				stack := remoteStack{Number: 10}
				for _, n := range test.numbers {
					stack.PullRequests = append(stack.PullRequests, remoteStackPullRequest{Number: n})
				}
				writeJSON(t, w, []remoteStack{stack})
			})
			defer server.Close()
			client := testClient(t, t.TempDir(), server)
			err := client.ValidateMergeScope(context.Background(), testRepository(server), test.members)
			if (err != nil) != test.wantErr {
				t.Fatalf("error = %v", err)
			}
		})
	}
}

func TestMergeHTTPFailuresPreserveClassification(t *testing.T) {
	server := newGitHubServer(t, func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		writeJSON(t, w, map[string]string{"message": "operation expired"})
	})
	defer server.Close()
	client := testClient(t, t.TempDir(), server)
	_, err := client.PollMerge(context.Background(), testRepository(server), 42, "expired")
	var apiErr *APIError
	if !errors.As(err, &apiErr) || apiErr.StatusCode != 404 {
		t.Fatalf("error = %v", err)
	}
}
