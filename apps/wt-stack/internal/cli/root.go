package cli

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"strings"

	"github.com/chadxz/prompts/apps/wt-stack/internal/gitrepo"
	stackmanager "github.com/chadxz/prompts/apps/wt-stack/internal/stack"
	"github.com/chadxz/prompts/apps/wt-stack/internal/state"
	"github.com/spf13/cobra"
)

const schemaVersion = 1

var version = "dev"

type commandManager interface {
	SetDryRun(bool)
	Init(context.Context, stackmanager.InitOptions) (*state.Stack, error)
	Add(context.Context, stackmanager.AddOptions) (*state.Branch, error)
	WorktreeForBranch(
		context.Context,
		string,
	) (gitrepo.Worktree, bool, error)
	Status(context.Context, string) ([]stackmanager.Status, error)
	Rebase(context.Context, stackmanager.RebaseOptions) error
	Continue(context.Context) error
	Abort(context.Context) error
	Push(context.Context, string) error
	Refresh(context.Context, string) error
	Submit(context.Context, string) error
	Doctor(context.Context, string) (map[string]string, error)
}

type options struct {
	json      bool
	dryRun    bool
	stackName string
	out       io.Writer
	err       io.Writer
	manager   commandManager
}

type commandResult struct {
	Schema   int                    `json:"schemaVersion"`
	Status   string                 `json:"status"`
	Command  string                 `json:"command"`
	Stack    *state.Stack           `json:"stack,omitempty"`
	Branch   *state.Branch          `json:"branch,omitempty"`
	Stacks   *[]stackmanager.Status `json:"stacks,omitempty"`
	Checks   map[string]string      `json:"checks,omitempty"`
	Message  string                 `json:"message,omitempty"`
	Worktree string                 `json:"worktree,omitempty"`
}

type errorResult struct {
	Schema   int    `json:"schemaVersion"`
	Status   string `json:"status"`
	Error    string `json:"error"`
	Branch   string `json:"branch,omitempty"`
	Stack    string `json:"stack,omitempty"`
	Worktree string `json:"worktree,omitempty"`
	Continue string `json:"continue,omitempty"`
	Abort    string `json:"abort,omitempty"`
}

// Execute runs the CLI and returns its process exit code.
func Execute() int {
	return execute(os.Args[1:], os.Stdout, os.Stderr, nil)
}

func execute(
	args []string,
	out io.Writer,
	errOut io.Writer,
	manager commandManager,
) int {
	opts := &options{out: out, err: errOut, manager: manager}
	root := newRootCommand(opts)
	root.SetArgs(args)
	if err := root.Execute(); err != nil {
		return opts.printError(err)
	}
	return 0
}

func newRootCommand(opts *options) *cobra.Command {
	root := &cobra.Command{
		Use:           "wt-stack",
		Short:         "Manage stacked branches across bare Git worktrees",
		Version:       version,
		SilenceErrors: true,
		SilenceUsage:  true,
	}
	root.SetOut(opts.out)
	root.SetErr(opts.err)
	root.PersistentFlags().BoolVar(&opts.json, "json", false,
		"emit machine-readable JSON")
	root.PersistentFlags().BoolVar(&opts.dryRun, "dry-run", false,
		"validate and plan without changing branches, state, or remotes")
	root.PersistentFlags().StringVar(&opts.stackName, "stack", "",
		"select a stack by name")

	root.AddCommand(
		newInitCommand(opts),
		newAddCommand(opts),
		newStatusCommand(opts),
		newRebaseCommand(opts),
		newContinueCommand(opts),
		newAbortCommand(opts),
		newPushCommand(opts),
		newRefreshCommand(opts),
		newSubmitCommand(opts),
		newSyncCommand(opts),
		newDoctorCommand(opts),
	)
	return root
}

func newInitCommand(opts *options) *cobra.Command {
	var name string
	var remote string
	var trunk string
	command := &cobra.Command{
		Use:   "init [branches...]",
		Short: "Adopt an existing linear branch chain",
		RunE: func(command *cobra.Command, args []string) error {
			manager, err := opts.getManager(command.Context())
			if err != nil {
				return err
			}
			stack, err := manager.Init(command.Context(), stackmanager.InitOptions{
				Name:     name,
				Remote:   remote,
				Trunk:    trunk,
				Branches: args,
			})
			if err != nil {
				return err
			}
			return opts.print(commandResult{
				Status:  opts.successStatus(),
				Command: "init",
				Stack:   stack,
				Message: fmt.Sprintf("Initialized stack %s", stack.Name),
			})
		},
	}
	command.Flags().StringVar(&name, "name", "", "stack name")
	command.Flags().StringVar(&remote, "remote", "origin", "Git remote")
	command.Flags().StringVar(&trunk, "base", "main", "trunk branch")
	return command
}

func newAddCommand(opts *options) *cobra.Command {
	var path string
	command := &cobra.Command{
		Use:   "add <branch>",
		Short: "Create a branch in a new sibling worktree",
		Args:  cobra.ExactArgs(1),
		RunE: func(command *cobra.Command, args []string) error {
			manager, err := opts.getManager(command.Context())
			if err != nil {
				return err
			}
			branch, err := manager.Add(command.Context(), stackmanager.AddOptions{
				StackName: opts.stackName,
				Branch:    args[0],
				Path:      path,
			})
			if err != nil {
				return err
			}
			worktree := ""
			if !opts.dryRun {
				if found, exists, findErr := manager.WorktreeForBranch(
					command.Context(),
					branch.Name,
				); findErr == nil && exists {
					worktree = found.Path
				}
			}
			return opts.print(commandResult{
				Status:   opts.successStatus(),
				Command:  "add",
				Branch:   branch,
				Worktree: worktree,
				Message:  fmt.Sprintf("Added branch %s", branch.Name),
			})
		},
	}
	command.Flags().StringVar(&path, "path", "",
		"worktree path relative to the repository container")
	return command
}

func newStatusCommand(opts *options) *cobra.Command {
	return &cobra.Command{
		Use:   "status",
		Short: "Show stacks, branches, worktrees, and pull requests",
		Args:  cobra.NoArgs,
		RunE: func(command *cobra.Command, _ []string) error {
			manager, err := opts.getManager(command.Context())
			if err != nil {
				return err
			}
			stacks, err := manager.Status(command.Context(), opts.stackName)
			if err != nil {
				return err
			}
			if opts.json {
				return opts.print(commandResult{
					Status:  "ok",
					Command: "status",
					Stacks:  &stacks,
				})
			}
			printHumanStatus(opts.out, stacks)
			return nil
		},
	}
}

func newRebaseCommand(opts *options) *cobra.Command {
	var noFetch bool
	command := &cobra.Command{
		Use:   "rebase",
		Short: "Cascade a rebase through branch-owning worktrees",
		Args:  cobra.NoArgs,
		RunE: func(command *cobra.Command, _ []string) error {
			manager, err := opts.getManager(command.Context())
			if err != nil {
				return err
			}
			if err := manager.Rebase(command.Context(), stackmanager.RebaseOptions{
				StackName: opts.stackName,
				Fetch:     !noFetch,
			}); err != nil {
				return err
			}
			return opts.print(commandResult{
				Status:  opts.successStatus(),
				Command: "rebase",
				Message: "Rebased stack",
			})
		},
	}
	command.Flags().BoolVar(&noFetch, "no-fetch", false,
		"skip fetching the remote trunk")
	return command
}

func newContinueCommand(opts *options) *cobra.Command {
	return &cobra.Command{
		Use:   "continue",
		Short: "Continue a paused cascading rebase",
		Args:  cobra.NoArgs,
		RunE: func(command *cobra.Command, _ []string) error {
			manager, err := opts.getManager(command.Context())
			if err != nil {
				return err
			}
			if err := manager.Continue(command.Context()); err != nil {
				return err
			}
			return opts.print(commandResult{
				Status:  opts.successStatus(),
				Command: "continue",
				Message: "Continued rebase",
			})
		},
	}
}

func newAbortCommand(opts *options) *cobra.Command {
	return &cobra.Command{
		Use:   "abort",
		Short: "Abort a cascade and restore every original branch",
		Args:  cobra.NoArgs,
		RunE: func(command *cobra.Command, _ []string) error {
			manager, err := opts.getManager(command.Context())
			if err != nil {
				return err
			}
			if err := manager.Abort(command.Context()); err != nil {
				return err
			}
			return opts.print(commandResult{
				Status:  opts.successStatus(),
				Command: "abort",
				Message: "Aborted rebase and restored branches",
			})
		},
	}
}

func newPushCommand(opts *options) *cobra.Command {
	return &cobra.Command{
		Use:   "push",
		Short: "Push active branches atomically with force-with-lease",
		Args:  cobra.NoArgs,
		RunE: func(command *cobra.Command, _ []string) error {
			manager, err := opts.getManager(command.Context())
			if err != nil {
				return err
			}
			if err := manager.Push(command.Context(), opts.stackName); err != nil {
				return err
			}
			return opts.print(commandResult{
				Status:  opts.successStatus(),
				Command: "push",
				Message: "Pushed stack",
			})
		},
	}
}

func newRefreshCommand(opts *options) *cobra.Command {
	return &cobra.Command{
		Use:   "refresh",
		Short: "Refresh pull request metadata from GitHub",
		Args:  cobra.NoArgs,
		RunE: func(command *cobra.Command, _ []string) error {
			manager, err := opts.getManager(command.Context())
			if err != nil {
				return err
			}
			if err := manager.Refresh(command.Context(), opts.stackName); err != nil {
				return err
			}
			return opts.print(commandResult{
				Status:  opts.successStatus(),
				Command: "refresh",
				Message: "Refreshed pull request state",
			})
		},
	}
}

func newSubmitCommand(opts *options) *cobra.Command {
	return &cobra.Command{
		Use:   "submit",
		Short: "Push branches and create or update the GitHub Stack",
		Args:  cobra.NoArgs,
		RunE: func(command *cobra.Command, _ []string) error {
			manager, err := opts.getManager(command.Context())
			if err != nil {
				return err
			}
			if err := manager.Submit(command.Context(), opts.stackName); err != nil {
				return err
			}
			return opts.print(commandResult{
				Status:  opts.successStatus(),
				Command: "submit",
				Message: "Submitted stack",
			})
		},
	}
}

func newSyncCommand(opts *options) *cobra.Command {
	return &cobra.Command{
		Use:   "sync",
		Short: "Refresh, rebase, push, and submit the selected stack",
		Args:  cobra.NoArgs,
		RunE: func(command *cobra.Command, _ []string) error {
			manager, err := opts.getManager(command.Context())
			if err != nil {
				return err
			}
			if err := manager.Refresh(command.Context(), opts.stackName); err != nil {
				return err
			}
			if err := manager.Rebase(command.Context(), stackmanager.RebaseOptions{
				StackName: opts.stackName,
				Fetch:     true,
			}); err != nil {
				return err
			}
			if err := manager.Submit(command.Context(), opts.stackName); err != nil {
				return err
			}
			return opts.print(commandResult{
				Status:  opts.successStatus(),
				Command: "sync",
				Message: "Synchronized stack",
			})
		},
	}
}

func newDoctorCommand(opts *options) *cobra.Command {
	return &cobra.Command{
		Use:   "doctor",
		Short: "Verify GitHub authentication and repository preview support",
		Args:  cobra.NoArgs,
		RunE: func(command *cobra.Command, _ []string) error {
			manager, err := opts.getManager(command.Context())
			if err != nil {
				return err
			}
			checks, err := manager.Doctor(
				command.Context(),
				opts.stackName,
			)
			if err != nil {
				return err
			}
			return opts.print(commandResult{
				Status:  "ok",
				Command: "doctor",
				Checks:  checks,
				Message: "Environment is ready",
			})
		},
	}
}

func (o *options) getManager(ctx context.Context) (commandManager, error) {
	if o.manager != nil {
		o.manager.SetDryRun(o.dryRun)
		return o.manager, nil
	}
	workingDirectory, err := os.Getwd()
	if err != nil {
		return nil, fmt.Errorf("determining working directory: %w", err)
	}
	repository, err := gitrepo.Discover(ctx, workingDirectory)
	if err != nil {
		return nil, err
	}
	interactiveOut := o.out
	interactiveErr := o.err
	if o.json {
		interactiveOut = io.Discard
		interactiveErr = io.Discard
	}
	manager := stackmanager.NewManager(repository, interactiveOut, interactiveErr)
	manager.SetDryRun(o.dryRun)
	o.manager = manager
	return manager, nil
}

func (o *options) print(result commandResult) error {
	result.Schema = schemaVersion
	if o.json {
		encoder := json.NewEncoder(o.out)
		encoder.SetEscapeHTML(false)
		return encoder.Encode(result)
	}
	if result.Message != "" {
		if o.dryRun {
			_, err := fmt.Fprintf(
				o.out,
				"Planned without changes: %s\n",
				result.Command,
			)
			return err
		}
		_, err := fmt.Fprintln(o.out, result.Message)
		return err
	}
	return nil
}

func (o *options) printError(err error) int {
	exitCode := 1
	result := errorResult{
		Schema: schemaVersion,
		Status: "error",
		Error:  err.Error(),
	}
	var conflict *stackmanager.RebaseConflictError
	if errors.As(err, &conflict) {
		exitCode = 3
		result.Status = "conflict"
		result.Stack = conflict.StackName
		result.Branch = conflict.Branch
		result.Worktree = conflict.Worktree
		result.Continue = "wt-stack continue"
		result.Abort = "wt-stack abort"
	}
	if o.json {
		encoder := json.NewEncoder(o.err)
		encoder.SetEscapeHTML(false)
		_ = encoder.Encode(result)
	} else {
		_, _ = fmt.Fprintln(o.err, err)
		if conflict != nil {
			_, _ = fmt.Fprintf(o.err,
				"Resolve conflicts in %s, then run wt-stack continue.\n",
				conflict.Worktree,
			)
			_, _ = fmt.Fprintln(o.err,
				"Run wt-stack abort to restore every branch.")
		}
	}
	return exitCode
}

func (o *options) successStatus() string {
	if o.dryRun {
		return "planned"
	}
	return "ok"
}

func printHumanStatus(writer io.Writer, stacks []stackmanager.Status) {
	for stackIndex, stack := range stacks {
		if stackIndex > 0 {
			_, _ = fmt.Fprintln(writer)
		}
		_, _ = fmt.Fprintf(writer, "%s (%s/%s)\n",
			stack.Name, stack.Remote, stack.Trunk)
		for _, branch := range stack.Branches {
			flags := make([]string, 0, 4)
			if branch.Worktree == "" {
				flags = append(flags, "missing-worktree")
			} else if !branch.Clean {
				flags = append(flags, "dirty")
			}
			if branch.Drifted {
				flags = append(flags, "unrecorded-commits")
			}
			if branch.PullRequest != nil {
				if branch.PullRequest.Merged {
					flags = append(flags,
						fmt.Sprintf("merged-pr-%d", branch.PullRequest.Number))
				} else {
					flags = append(flags,
						fmt.Sprintf("pr-%d", branch.PullRequest.Number))
				}
			}
			suffix := ""
			if len(flags) > 0 {
				suffix = " [" + strings.Join(flags, ", ") + "]"
			}
			_, _ = fmt.Fprintf(writer, "  %s %s%s\n",
				shortSHA(branch.Head), branch.Name, suffix)
			if branch.Worktree != "" {
				_, _ = fmt.Fprintf(writer, "    %s\n", branch.Worktree)
			}
		}
	}
}

func shortSHA(sha string) string {
	if len(sha) <= 8 {
		return sha
	}
	return sha[:8]
}
