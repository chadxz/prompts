package cli

import (
	"fmt"
	"time"

	"github.com/chadxz/prompts/apps/wt-stack/internal/github"
	stackmanager "github.com/chadxz/prompts/apps/wt-stack/internal/stack"
	"github.com/spf13/cobra"
)

type mergeCommandError struct {
	result *github.MergeResult
	err    error
}

func (e *mergeCommandError) Error() string {
	if e.result != nil && e.result.UUID != "" {
		return fmt.Sprintf("%v; inspect with wt-stack merge --pr %d --resume %s", e.err, e.result.PullRequest, e.result.UUID)
	}
	return e.err.Error()
}
func (e *mergeCommandError) Unwrap() error { return e.err }

func newMergeCommand(opts *options) *cobra.Command {
	var mergeOptions stackmanager.MergeOptions
	command := &cobra.Command{
		Use: "merge", Short: "Merge published branches through the selected stack tip",
		Args: cobra.NoArgs,
		RunE: func(command *cobra.Command, _ []string) error {
			manager, err := opts.getManager(command.Context())
			if err != nil {
				return err
			}
			mergeOptions.StackName = opts.stackName
			result, err := manager.Merge(command.Context(), mergeOptions)
			if err != nil {
				return &mergeCommandError{result: result, err: err}
			}
			message := fmt.Sprintf("Pull request #%d: %s", result.PullRequest, result.Status)
			if result.Status == "enqueued" {
				message += " (accepted by merge queue; not yet merged)"
			}
			if result.Status == "pending" {
				message += fmt.Sprintf("; resume with wt-stack --stack %q merge --pr %d --resume %s", mergeOptions.StackName, result.PullRequest, result.UUID)
				if result.Existing {
					message += " (existing request; its options may differ)"
				}
			}
			return opts.print(commandResult{Status: opts.successStatus(), Command: "merge", Merge: result, Message: message})
		},
	}
	command.Flags().StringVar(&mergeOptions.Through, "through", "", "merge through this local branch (defaults to the stack tip)")
	command.Flags().StringVar(&mergeOptions.Method, "merge-method", "", "merge, squash, or rebase (omit for GitHub default; direct merges use a merge commit)")
	command.Flags().DurationVar(&mergeOptions.Timeout, "timeout", 2*time.Minute, "maximum time to wait for a pending merge")
	command.Flags().StringVar(&mergeOptions.Resume, "resume", "", "poll an existing merge UUID without submitting another request")
	command.Flags().IntVar(&mergeOptions.PullRequest, "pr", 0, "pull request number for --resume")
	return command
}
