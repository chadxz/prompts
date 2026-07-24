// Package state persists worktree stack metadata in Git's common directory.
package state

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"syscall"
)

const (
	currentVersion = 1
	stateFileName  = "wt-stack.json"
	lockFileName   = "wt-stack.lock"
)

// File is the repository-wide state shared by every linked worktree.
type File struct {
	Version int            `json:"version"`
	Stacks  []Stack        `json:"stacks"`
	Rebase  *RebaseSession `json:"rebase,omitempty"`
}

// Stack describes an ordered branch chain rooted at a remote trunk branch.
type Stack struct {
	Name     string   `json:"name"`
	Remote   string   `json:"remote"`
	Trunk    string   `json:"trunk"`
	Branches []Branch `json:"branches"`
}

// Branch records the old parent and head needed for a safe cascading rebase.
type Branch struct {
	Name        string       `json:"name"`
	Base        string       `json:"base"`
	Head        string       `json:"head"`
	PullRequest *PullRequest `json:"pullRequest,omitempty"`
}

// PullRequest records the remote pull request associated with a branch.
type PullRequest struct {
	Number int    `json:"number"`
	URL    string `json:"url"`
	Base   string `json:"base"`
	State  string `json:"state"`
	Merged bool   `json:"merged"`
}

// RebaseSession stores enough information to continue or abort a cascade.
type RebaseSession struct {
	StackName        string            `json:"stackName"`
	CurrentIndex     int               `json:"currentIndex"`
	CurrentWorktree  string            `json:"currentWorktree,omitempty"`
	OriginalBranches map[string]string `json:"originalBranches"`
	OriginalStack    Stack             `json:"originalStack"`
}

// Store owns the state and lock files in a repository's common Git directory.
type Store struct {
	path     string
	lockPath string
}

// LockedStore is an exclusively locked state store.
type LockedStore struct {
	store *Store
	lock  *os.File
}

// NewStore creates a state store for a common Git directory.
func NewStore(commonDir string) *Store {
	return &Store{
		path:     filepath.Join(commonDir, stateFileName),
		lockPath: filepath.Join(commonDir, lockFileName),
	}
}

// Path returns the state file path.
func (s *Store) Path() string {
	return s.path
}

// Lock acquires the repository-wide state lock.
func (s *Store) Lock() (*LockedStore, error) {
	lock, err := os.OpenFile(s.lockPath, os.O_CREATE|os.O_RDWR, 0o644)
	if err != nil {
		return nil, fmt.Errorf("opening state lock: %w", err)
	}
	if err := syscall.Flock(int(lock.Fd()), syscall.LOCK_EX); err != nil {
		_ = lock.Close()
		return nil, fmt.Errorf("locking state: %w", err)
	}
	return &LockedStore{store: s, lock: lock}, nil
}

// Close releases the repository-wide state lock.
func (s *LockedStore) Close() error {
	if s == nil || s.lock == nil {
		return nil
	}
	unlockErr := syscall.Flock(int(s.lock.Fd()), syscall.LOCK_UN)
	closeErr := s.lock.Close()
	if unlockErr != nil {
		return fmt.Errorf("unlocking state: %w", unlockErr)
	}
	if closeErr != nil {
		return fmt.Errorf("closing state lock: %w", closeErr)
	}
	return nil
}

// Load reads and validates the current state.
func (s *LockedStore) Load() (*File, error) {
	data, err := os.ReadFile(s.store.path)
	if errors.Is(err, os.ErrNotExist) {
		return &File{Version: currentVersion, Stacks: []Stack{}}, nil
	}
	if err != nil {
		return nil, fmt.Errorf("reading state: %w", err)
	}

	var file File
	if err := json.Unmarshal(data, &file); err != nil {
		return nil, fmt.Errorf("parsing state: %w", err)
	}
	if file.Version > currentVersion {
		return nil, fmt.Errorf(
			"state version %d is newer than supported version %d",
			file.Version,
			currentVersion,
		)
	}
	if file.Stacks == nil {
		file.Stacks = []Stack{}
	}
	return &file, nil
}

// Save atomically writes the current state.
func (s *LockedStore) Save(file *File) error {
	file.Version = currentVersion
	if file.Stacks == nil {
		file.Stacks = []Stack{}
	}
	data, err := json.MarshalIndent(file, "", "  ")
	if err != nil {
		return fmt.Errorf("encoding state: %w", err)
	}
	data = append(data, '\n')

	temp, err := os.CreateTemp(filepath.Dir(s.store.path), ".wt-stack-*.json")
	if err != nil {
		return fmt.Errorf("creating temporary state: %w", err)
	}
	tempPath := temp.Name()
	defer func() {
		_ = os.Remove(tempPath)
	}()

	if err := temp.Chmod(0o644); err != nil {
		_ = temp.Close()
		return fmt.Errorf("setting temporary state permissions: %w", err)
	}
	if _, err := temp.Write(data); err != nil {
		_ = temp.Close()
		return fmt.Errorf("writing temporary state: %w", err)
	}
	if err := temp.Sync(); err != nil {
		_ = temp.Close()
		return fmt.Errorf("syncing temporary state: %w", err)
	}
	if err := temp.Close(); err != nil {
		return fmt.Errorf("closing temporary state: %w", err)
	}
	if err := os.Rename(tempPath, s.store.path); err != nil {
		return fmt.Errorf("replacing state: %w", err)
	}
	return nil
}

// FindStack returns a stack by name.
func (f *File) FindStack(name string) (*Stack, bool) {
	for index := range f.Stacks {
		if f.Stacks[index].Name == name {
			return &f.Stacks[index], true
		}
	}
	return nil, false
}

// FindStackForBranch returns the stack that contains a branch.
func (f *File) FindStackForBranch(branch string) (*Stack, bool) {
	for stackIndex := range f.Stacks {
		for _, candidate := range f.Stacks[stackIndex].Branches {
			if candidate.Name == branch {
				return &f.Stacks[stackIndex], true
			}
		}
	}
	return nil, false
}

// CloneStack returns a deep copy suitable for rollback state.
func CloneStack(stack Stack) Stack {
	clone := stack
	clone.Branches = make([]Branch, len(stack.Branches))
	copy(clone.Branches, stack.Branches)
	for index, branch := range stack.Branches {
		if branch.PullRequest == nil {
			continue
		}
		pullRequest := *branch.PullRequest
		clone.Branches[index].PullRequest = &pullRequest
	}
	return clone
}
