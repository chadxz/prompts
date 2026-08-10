package cli

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/chadxz/prompts/apps/wt-stack/internal/gitrepo"
	stackmanager "github.com/chadxz/prompts/apps/wt-stack/internal/stack"
	"github.com/chadxz/prompts/apps/wt-stack/internal/state"
)

func TestExecuteDispatchesJSONCommands(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name        string
		args        []string
		wantCommand string
		wantCalls   []string
	}{
		{
			name:        "init",
			args:        []string{"--json", "init", "--name", "delivery", "feature"},
			wantCommand: "init",
			wantCalls:   []string{"init"},
		},
		{
			name:        "add",
			args:        []string{"--json", "--stack", "delivery", "add", "feature-two"},
			wantCommand: "add",
			wantCalls:   []string{"add", "worktree"},
		},
		{
			name:        "status",
			args:        []string{"--json", "status"},
			wantCommand: "status",
			wantCalls:   []string{"status"},
		},
		{
			name:        "rebase",
			args:        []string{"--json", "rebase", "--no-fetch"},
			wantCommand: "rebase",
			wantCalls:   []string{"rebase"},
		},
		{
			name:        "continue",
			args:        []string{"--json", "continue"},
			wantCommand: "continue",
			wantCalls:   []string{"continue"},
		},
		{
			name:        "abort",
			args:        []string{"--json", "abort"},
			wantCommand: "abort",
			wantCalls:   []string{"abort"},
		},
		{
			name:        "push",
			args:        []string{"--json", "push"},
			wantCommand: "push",
			wantCalls:   []string{"push"},
		},
		{
			name:        "refresh",
			args:        []string{"--json", "refresh"},
			wantCommand: "refresh",
			wantCalls:   []string{"refresh"},
		},
		{
			name:        "submit",
			args:        []string{"--json", "submit"},
			wantCommand: "submit",
			wantCalls:   []string{"submit"},
		},
		{
			name:        "sync",
			args:        []string{"--json", "sync"},
			wantCommand: "sync",
			wantCalls:   []string{"refresh", "rebase", "submit"},
		},
		{
			name:        "unstack",
			args:        []string{"--json", "unstack"},
			wantCommand: "unstack",
			wantCalls:   []string{"unstack"},
		},
		{
			name:        "delete alias",
			args:        []string{"--json", "delete"},
			wantCommand: "unstack",
			wantCalls:   []string{"unstack"},
		},
		{
			name:        "doctor",
			args:        []string{"--json", "doctor"},
			wantCommand: "doctor",
			wantCalls:   []string{"doctor"},
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()

			manager := &fakeCommandManager{}
			var out bytes.Buffer
			var errOut bytes.Buffer
			if code := execute(test.args, &out, &errOut, manager); code != 0 {
				t.Fatalf("exit code = %d, stderr = %s", code, errOut.String())
			}

			var result commandResult
			if err := json.Unmarshal(out.Bytes(), &result); err != nil {
				t.Fatalf("decode output: %v\n%s", err, out.String())
			}
			if result.Schema != schemaVersion ||
				result.Status != "ok" ||
				result.Command != test.wantCommand {
				t.Fatalf("unexpected result: %#v", result)
			}
			if strings.Join(manager.calls, ",") != strings.Join(test.wantCalls, ",") {
				t.Fatalf("calls = %v, want %v", manager.calls, test.wantCalls)
			}
		})
	}
}

func TestExecuteDryRunUsesPlannedStatus(t *testing.T) {
	t.Parallel()

	for _, command := range []string{
		"continue",
		"abort",
		"push",
		"submit",
		"sync",
		"unstack",
	} {
		t.Run(command, func(t *testing.T) {
			t.Parallel()

			manager := &fakeCommandManager{}
			var out bytes.Buffer
			var errOut bytes.Buffer
			code := execute(
				[]string{"--json", "--dry-run", command},
				&out,
				&errOut,
				manager,
			)
			if code != 0 {
				t.Fatalf("exit code = %d, stderr = %s", code, errOut.String())
			}
			var result commandResult
			if err := json.Unmarshal(out.Bytes(), &result); err != nil {
				t.Fatalf("decode output: %v", err)
			}
			if result.Status != "planned" || !manager.dryRun {
				t.Fatalf("result = %#v, manager dry-run = %t", result, manager.dryRun)
			}
		})
	}
}

func TestExecuteDryRunHumanOutputDescribesAPlan(t *testing.T) {
	t.Parallel()

	var out bytes.Buffer
	var errOut bytes.Buffer
	code := execute(
		[]string{"--dry-run", "push"},
		&out,
		&errOut,
		&fakeCommandManager{},
	)
	if code != 0 {
		t.Fatalf("exit code = %d, stderr = %s", code, errOut.String())
	}
	if got := strings.TrimSpace(out.String()); got !=
		"Planned without changes: push" {
		t.Fatalf("dry-run output = %q", got)
	}
}

func TestExecutePreservesDraftSubmissionOption(t *testing.T) {
	t.Parallel()

	for _, command := range []string{"submit", "sync"} {
		t.Run(command, func(t *testing.T) {
			t.Parallel()

			manager := &fakeCommandManager{}
			var errOut bytes.Buffer
			code := execute(
				[]string{"--stack", "delivery", command, "--draft"},
				&bytes.Buffer{},
				&errOut,
				manager,
			)
			if code != 0 {
				t.Fatalf("exit code = %d, stderr = %s", code, errOut.String())
			}
			if manager.submitOptions.StackName != "delivery" ||
				!manager.submitOptions.Draft {
				t.Fatalf("submit options = %#v", manager.submitOptions)
			}
		})
	}
}

func TestExecuteUnstackLocalLeavesGitHubUntouched(t *testing.T) {
	t.Parallel()

	manager := &fakeCommandManager{}
	var out bytes.Buffer
	var errOut bytes.Buffer
	code := execute(
		[]string{"--json", "unstack", "--local"},
		&out,
		&errOut,
		manager,
	)
	if code != 0 {
		t.Fatalf("exit code = %d, stderr = %s", code, errOut.String())
	}
	if !manager.unstackLocal {
		t.Fatal("unstack did not preserve the local-only option")
	}
	var result commandResult
	if err := json.Unmarshal(out.Bytes(), &result); err != nil {
		t.Fatalf("decode output: %v", err)
	}
	if result.LocalRemoved == nil ||
		!*result.LocalRemoved ||
		result.RemoteRemoved != nil {
		t.Fatalf("unexpected removal result: %#v", result)
	}
}

func TestExecuteStatusJSONIncludesEmptyStacks(t *testing.T) {
	t.Parallel()

	var out bytes.Buffer
	code := execute(
		[]string{"--json", "status"},
		&out,
		&bytes.Buffer{},
		&fakeCommandManager{},
	)
	if code != 0 {
		t.Fatalf("exit code = %d", code)
	}
	var result map[string]json.RawMessage
	if err := json.Unmarshal(out.Bytes(), &result); err != nil {
		t.Fatalf("decode status: %v", err)
	}
	if got, exists := result["stacks"]; !exists || string(got) != "[]" {
		t.Fatalf("stacks = %s, exists = %t", got, exists)
	}
}

func TestExecuteRejectsUnexpectedArguments(t *testing.T) {
	t.Parallel()

	for _, command := range []string{
		"status",
		"rebase",
		"continue",
		"abort",
		"push",
		"refresh",
		"submit",
		"sync",
		"unstack",
		"doctor",
	} {
		t.Run(command, func(t *testing.T) {
			t.Parallel()

			var errOut bytes.Buffer
			code := execute(
				[]string{"--json", command, "unexpected"},
				&bytes.Buffer{},
				&errOut,
				&fakeCommandManager{},
			)
			if code != 1 {
				t.Fatalf("exit code = %d, want 1", code)
			}
			var result errorResult
			if err := json.Unmarshal(errOut.Bytes(), &result); err != nil {
				t.Fatalf("decode error: %v\n%s", err, errOut.String())
			}
			if result.Schema != schemaVersion ||
				!strings.Contains(result.Error, "unknown command") {
				t.Fatalf("unexpected error: %#v", result)
			}
		})
	}
}

func TestExecuteReturnsStructuredConflict(t *testing.T) {
	t.Parallel()

	manager := &fakeCommandManager{
		rebaseErr: &stackmanager.RebaseConflictError{
			StackName: "delivery",
			Branch:    "feature-one",
			Worktree:  "/worktrees/feature-one",
		},
	}
	var errOut bytes.Buffer
	code := execute(
		[]string{"--json", "rebase"},
		&bytes.Buffer{},
		&errOut,
		manager,
	)
	if code != 3 {
		t.Fatalf("exit code = %d, want 3", code)
	}
	var result errorResult
	if err := json.Unmarshal(errOut.Bytes(), &result); err != nil {
		t.Fatalf("decode conflict: %v", err)
	}
	if result.Status != "conflict" ||
		result.Continue != "wt-stack continue" ||
		result.Abort != "wt-stack abort" {
		t.Fatalf("unexpected conflict: %#v", result)
	}
}

func TestExecutePropagatesManagerErrors(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name string
		args []string
	}{
		{name: "init", args: []string{"init", "feature"}},
		{name: "add", args: []string{"add", "feature"}},
		{name: "status", args: []string{"status"}},
		{name: "rebase", args: []string{"rebase"}},
		{name: "continue", args: []string{"continue"}},
		{name: "abort", args: []string{"abort"}},
		{name: "push", args: []string{"push"}},
		{name: "refresh", args: []string{"refresh"}},
		{name: "submit", args: []string{"submit"}},
		{name: "sync", args: []string{"sync"}},
		{name: "unstack", args: []string{"unstack"}},
		{name: "doctor", args: []string{"doctor"}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()

			var errOut bytes.Buffer
			code := execute(
				test.args,
				&bytes.Buffer{},
				&errOut,
				&fakeCommandManager{
					commandErr: errors.New("manager unavailable"),
				},
			)
			if code != 1 ||
				strings.TrimSpace(errOut.String()) != "manager unavailable" {
				t.Fatalf("exit code = %d, stderr = %q", code, errOut.String())
			}
		})
	}
}

func TestExecutePrintsHumanMutationResult(t *testing.T) {
	t.Parallel()

	var out bytes.Buffer
	if code := execute(
		[]string{"init", "--name", "delivery", "feature"},
		&out,
		&bytes.Buffer{},
		&fakeCommandManager{},
	); code != 0 {
		t.Fatalf("exit code = %d", code)
	}
	if got := strings.TrimSpace(out.String()); got != "Initialized stack delivery" {
		t.Fatalf("output = %q", got)
	}
}

func TestPrintHumanStatus(t *testing.T) {
	t.Parallel()

	var out bytes.Buffer
	printHumanStatus(&out, []stackmanager.Status{{
		Name:   "delivery",
		Remote: "origin",
		Trunk:  "main",
		Branches: []stackmanager.BranchStatus{
			{
				Name:     "feature-one",
				Worktree: "/worktrees/feature-one",
				Clean:    true,
				Head:     "1234567890",
			},
			{
				Name:    "feature-two",
				Clean:   false,
				Head:    "abcdef",
				Drifted: true,
				PullRequest: &state.PullRequest{
					Number: 42,
					Merged: true,
				},
			},
		},
	}})
	output := out.String()
	for _, expected := range []string{
		"delivery (origin/main)",
		"12345678 feature-one",
		"/worktrees/feature-one",
		"abcdef feature-two [missing-worktree, unrecorded-commits, merged-pr-42]",
	} {
		if !strings.Contains(output, expected) {
			t.Fatalf("output does not contain %q:\n%s", expected, output)
		}
	}
}

func TestVersionAndHumanErrors(t *testing.T) {
	t.Parallel()

	var out bytes.Buffer
	if code := execute(
		[]string{"--version"},
		&out,
		&bytes.Buffer{},
		&fakeCommandManager{},
	); code != 0 {
		t.Fatalf("version exit code = %d", code)
	}
	if !strings.Contains(out.String(), version) {
		t.Fatalf("version output = %q", out.String())
	}

	manager := &fakeCommandManager{rebaseErr: errors.New("rebase unavailable")}
	var errOut bytes.Buffer
	if code := execute(
		[]string{"rebase"},
		&bytes.Buffer{},
		&errOut,
		manager,
	); code != 1 {
		t.Fatalf("error exit code = %d", code)
	}
	if got := strings.TrimSpace(errOut.String()); got != "rebase unavailable" {
		t.Fatalf("error output = %q", got)
	}
}

func TestJSONSchemaIsCurrentAndValidJSON(t *testing.T) {
	t.Parallel()

	path := filepath.Join("..", "..", "docs", "json-schema.json")
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read JSON schema: %v", err)
	}
	var schema struct {
		Definitions map[string]json.RawMessage `json:"$defs"`
	}
	if err := json.Unmarshal(data, &schema); err != nil {
		t.Fatalf("parse JSON schema: %v", err)
	}
	if len(schema.Definitions) == 0 ||
		!bytes.Contains(data, []byte(`"const": 1`)) ||
		!bytes.Contains(data, []byte(`"unstack"`)) {
		t.Fatalf("JSON schema does not describe version %d", schemaVersion)
	}

	pullRequest := &state.PullRequest{
		Number: 1,
		URL:    "https://github.com/example/repository/pull/1",
		Base:   "main",
		State:  "open",
	}
	branch := state.Branch{
		Name:        "feature",
		Base:        "base",
		Head:        "head",
		PullRequest: pullRequest,
	}
	statuses := []stackmanager.Status{{
		Name:   "delivery",
		Remote: "origin",
		Trunk:  "main",
		Branches: []stackmanager.BranchStatus{{
			Name:        "feature",
			Worktree:    "/worktrees/feature",
			Clean:       true,
			Head:        "head",
			Base:        "base",
			Drifted:     true,
			PullRequest: pullRequest,
		}},
	}}
	localRemoved := true
	remoteRemoved := false
	assertJSONKeysInSchema(t, data, commandResult{
		Schema:  schemaVersion,
		Status:  "ok",
		Command: "status",
		Stack: &state.Stack{
			Name:     "delivery",
			Remote:   "origin",
			Trunk:    "main",
			Branches: []state.Branch{branch},
		},
		Branch:        &branch,
		Stacks:        &statuses,
		Checks:        map[string]string{"githubAuth": "available"},
		Message:       "ok",
		Worktree:      "/worktrees/feature",
		LocalRemoved:  &localRemoved,
		RemoteRemoved: &remoteRemoved,
	})
	assertJSONKeysInSchema(t, data, errorResult{
		Schema:   schemaVersion,
		Status:   "conflict",
		Error:    "conflict",
		Branch:   "feature",
		Stack:    "delivery",
		Worktree: "/worktrees/feature",
		Continue: "wt-stack continue",
		Abort:    "wt-stack abort",
	})
}

func assertJSONKeysInSchema(t *testing.T, schema []byte, value any) {
	t.Helper()

	encoded, err := json.Marshal(value)
	if err != nil {
		t.Fatalf("marshal schema fixture: %v", err)
	}
	var decoded any
	if err := json.Unmarshal(encoded, &decoded); err != nil {
		t.Fatalf("decode schema fixture: %v", err)
	}
	var walk func(any)
	walk = func(current any) {
		switch typed := current.(type) {
		case map[string]any:
			for key, nested := range typed {
				if !bytes.Contains(schema, []byte(`"`+key+`"`)) {
					t.Errorf("schema is missing emitted JSON field %q", key)
				}
				if key == "checks" {
					continue
				}
				walk(nested)
			}
		case []any:
			for _, nested := range typed {
				walk(nested)
			}
		}
	}
	walk(decoded)
}

type fakeCommandManager struct {
	calls         []string
	dryRun        bool
	rebaseErr     error
	commandErr    error
	unstackLocal  bool
	submitOptions stackmanager.SubmitOptions
}

func (m *fakeCommandManager) SetDryRun(enabled bool) {
	m.dryRun = enabled
}

func (m *fakeCommandManager) Init(
	context.Context,
	stackmanager.InitOptions,
) (*state.Stack, error) {
	m.calls = append(m.calls, "init")
	if m.commandErr != nil {
		return nil, m.commandErr
	}
	return &state.Stack{Name: "delivery"}, nil
}

func (m *fakeCommandManager) Add(
	_ context.Context,
	options stackmanager.AddOptions,
) (*state.Branch, error) {
	m.calls = append(m.calls, "add")
	if m.commandErr != nil {
		return nil, m.commandErr
	}
	return &state.Branch{Name: options.Branch}, nil
}

func (m *fakeCommandManager) WorktreeForBranch(
	context.Context,
	string,
) (gitrepo.Worktree, bool, error) {
	m.calls = append(m.calls, "worktree")
	return gitrepo.Worktree{Path: "/worktrees/feature-two"}, true, nil
}

func (m *fakeCommandManager) Status(
	context.Context,
	string,
) ([]stackmanager.Status, error) {
	m.calls = append(m.calls, "status")
	if m.commandErr != nil {
		return nil, m.commandErr
	}
	return []stackmanager.Status{}, nil
}

func (m *fakeCommandManager) Rebase(
	context.Context,
	stackmanager.RebaseOptions,
) error {
	m.calls = append(m.calls, "rebase")
	if m.commandErr != nil {
		return m.commandErr
	}
	return m.rebaseErr
}

func (m *fakeCommandManager) Continue(context.Context) error {
	m.calls = append(m.calls, "continue")
	return m.commandErr
}

func (m *fakeCommandManager) Abort(context.Context) error {
	m.calls = append(m.calls, "abort")
	return m.commandErr
}

func (m *fakeCommandManager) Push(context.Context, string) error {
	m.calls = append(m.calls, "push")
	return m.commandErr
}

func (m *fakeCommandManager) Refresh(context.Context, string) error {
	m.calls = append(m.calls, "refresh")
	return m.commandErr
}

func (m *fakeCommandManager) Submit(
	_ context.Context,
	options stackmanager.SubmitOptions,
) error {
	m.calls = append(m.calls, "submit")
	m.submitOptions = options
	return m.commandErr
}

func (m *fakeCommandManager) Unstack(
	_ context.Context,
	_ string,
	localOnly bool,
) (bool, error) {
	m.calls = append(m.calls, "unstack")
	m.unstackLocal = localOnly
	return true, m.commandErr
}

func (m *fakeCommandManager) Doctor(
	context.Context,
	string,
) (map[string]string, error) {
	m.calls = append(m.calls, "doctor")
	if m.commandErr != nil {
		return nil, m.commandErr
	}
	return map[string]string{"githubAuth": "available"}, nil
}

var _ commandManager = (*fakeCommandManager)(nil)
