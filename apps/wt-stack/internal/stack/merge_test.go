package stack

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/chadxz/prompts/apps/wt-stack/internal/github"
	"github.com/chadxz/prompts/apps/wt-stack/internal/state"
)

func TestMergeValidatesBeforeSubmitting(t *testing.T) {
	t.Parallel()
	for _, scenario := range []string{"success", "dry-run", "draft", "closed", "missing PR", "head mismatch", "wrong base", "scope", "rebase", "merged", "target", "timeout", "method", "pr without resume", "resume without pr", "resume with method"} {
		t.Run(scenario, func(t *testing.T) {
			t.Parallel()
			file := unitStateFile()
			if scenario == "rebase" {
				file.Rebase = unitRebaseSession(file.Stacks[0])
			}
			manager, _, client, store := newUnitManager(t, file)
			client.pullRequests["feature-one"].HeadSHA = "head-one"
			client.mergeResult = &github.MergeResult{Status: "merged", PullRequest: 42}
			opts := MergeOptions{StackName: "delivery", Timeout: time.Second}
			switch scenario {
			case "dry-run":
				manager.SetDryRun(true)
			case "draft":
				client.pullRequests["feature-one"].Draft = true
			case "closed":
				client.pullRequests["feature-one"].State = "closed"
			case "missing PR":
				delete(client.pullRequests, "feature-one")
			case "head mismatch":
				client.pullRequests["feature-one"].HeadSHA = "other"
			case "wrong base":
				client.pullRequests["feature-one"].Base = "other"
			case "scope":
				client.scopeErr = errors.New("unselected remote PR")
			case "merged":
				client.pullRequests["feature-one"].Merged = true
			case "target":
				opts.Through = "other"
			case "timeout":
				opts.Timeout = 0
			case "method":
				opts.Method = "invalid"
			case "pr without resume":
				opts.PullRequest = 42
			case "resume without pr":
				opts.Resume = "request"
			case "resume with method":
				opts.Resume = "request"
				opts.PullRequest = 42
				opts.Method = "squash"
			}
			result, err := manager.Merge(context.Background(), opts)
			valid := scenario == "success" || scenario == "dry-run"
			if (err == nil) != valid {
				t.Fatalf("result=%#v, error=%v", result, err)
			}
			wantCalls := 0
			if scenario == "success" {
				wantCalls = 1
				if client.mergeSHA != "head-one" {
					t.Fatal("missing head guard")
				}
			}
			if client.mergeCalls != wantCalls || store.saves != 0 {
				t.Fatalf("calls=%d, saves=%d", client.mergeCalls, store.saves)
			}
			if scenario == "dry-run" && result.Status != "planned" {
				t.Fatalf("result=%#v", result)
			}
		})
	}
}

func TestMergeSelectsPrefixAndSkipsMergedHistory(t *testing.T) {
	t.Parallel()
	file := unitStateFile()
	file.Stacks[0].Branches = append([]state.Branch{{Name: "old"}}, file.Stacks[0].Branches...)
	file.Stacks[0].Branches = append(file.Stacks[0].Branches, state.Branch{Name: "unpublished-upper"})
	manager, _, client, _ := newUnitManager(t, file)
	client.pullRequests["old"] = &state.PullRequest{Number: 1, Merged: true}
	client.pullRequests["feature-one"].HeadSHA = "head-one"
	manager.SetDryRun(true)
	result, err := manager.Merge(context.Background(), MergeOptions{StackName: "delivery", Through: "feature-one", Timeout: time.Second})
	if err != nil || result.PullRequest != 42 {
		t.Fatalf("result=%#v, %v", result, err)
	}
}

func TestMergePendingAndResume(t *testing.T) {
	t.Parallel()
	for _, scenario := range []string{"merged", "enqueued", "failed", "timeout", "existing", "resume", "poll error", "cancel"} {
		t.Run(scenario, func(t *testing.T) {
			t.Parallel()
			manager, _, client, _ := newUnitManager(t, unitStateFile())
			client.pullRequests["feature-one"].HeadSHA = "head-one"
			client.mergeResult = &github.MergeResult{Status: "pending", PullRequest: 42, UUID: "request-1"}
			client.pollResult = &github.MergeResult{Status: "merged", PullRequest: 42, UUID: "request-1"}
			opts := MergeOptions{StackName: "delivery", Timeout: 2 * time.Second}
			ctx := context.Background()
			switch scenario {
			case "enqueued":
				client.pollResult.Status = "enqueued"
			case "failed":
				client.pollResult.Status = "failed"
				client.pollResult.Message = "rules failed"
			case "timeout":
				opts.Timeout = time.Millisecond
			case "existing":
				client.mergeResult.Existing = true
			case "resume":
				opts.Resume = "request-1"
				opts.PullRequest = 42
			case "poll error":
				opts.Resume = "request-1"
				opts.PullRequest = 42
				client.mergeErr = errors.New("network failed")
			case "cancel":
				var cancel context.CancelFunc
				ctx, cancel = context.WithCancel(ctx)
				cancel()
			}
			result, err := manager.Merge(ctx, opts)
			wantErr := scenario == "failed" || scenario == "poll error" || scenario == "cancel"
			if (err != nil) != wantErr {
				t.Fatalf("result=%#v, error=%v", result, err)
			}
			if scenario != "poll error" && (result == nil || result.UUID != "request-1") {
				t.Fatalf("lost request: %#v", result)
			}
			if scenario == "timeout" || scenario == "existing" || scenario == "cancel" {
				if client.pollCalls != 0 || result.Status != "pending" {
					t.Fatalf("unexpected poll: %#v", result)
				}
			}
			if scenario == "resume" && client.mergeCalls != 0 {
				t.Fatal("resume submitted another merge")
			}
			if scenario == "enqueued" && result.Status != "enqueued" {
				t.Fatal("queue admission reported merged")
			}
		})
	}
}
