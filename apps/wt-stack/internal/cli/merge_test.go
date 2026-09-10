package cli

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"

	"github.com/chadxz/prompts/apps/wt-stack/internal/github"
	stackmanager "github.com/chadxz/prompts/apps/wt-stack/internal/stack"
)

type mergeTestManager struct {
	fakeCommandManager
	result  *github.MergeResult
	err     error
	options stackmanager.MergeOptions
}

func (m *mergeTestManager) Merge(_ context.Context, options stackmanager.MergeOptions) (*github.MergeResult, error) {
	m.options = options
	return m.result, m.err
}

func TestMergeCommandReportsLifecycleAndRecovery(t *testing.T) {
	t.Parallel()
	for _, value := range []string{"merged", "enqueued", "pending", "failed"} {
		t.Run(value, func(t *testing.T) {
			t.Parallel()
			manager := &mergeTestManager{result: &github.MergeResult{Status: value, PullRequest: 42, UUID: "request-1"}}
			if value == "failed" {
				manager.err = errors.New("rules rejected merge")
			}
			var out, errOut bytes.Buffer
			code := execute([]string{"--json", "--stack", "delivery", "merge", "--through", "feature", "--merge-method", "squash", "--timeout", "5s"}, &out, &errOut, manager)
			raw := out.Bytes()
			if value == "failed" {
				if code != 1 {
					t.Fatal(code)
				}
				raw = errOut.Bytes()
			} else if code != 0 {
				t.Fatal(errOut.String())
			}
			var result struct {
				Merge *github.MergeResult `json:"merge"`
			}
			if err := json.Unmarshal(raw, &result); err != nil {
				t.Fatal(err)
			}
			if result.Merge == nil || result.Merge.Status != value || result.Merge.UUID != "request-1" {
				t.Fatalf("result=%s", raw)
			}
			if manager.options.Through != "feature" || manager.options.Method != "squash" || manager.options.StackName != "delivery" {
				t.Fatal(manager.options)
			}
			out.Reset()
			errOut.Reset()
			execute([]string{"merge"}, &out, &errOut, manager)
			if value == "enqueued" && !strings.Contains(out.String(), "not yet merged") {
				t.Fatal(out.String())
			}
			if value == "pending" && !strings.Contains(out.String(), "--resume request-1") {
				t.Fatal(out.String())
			}
		})
	}
}
