package state

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestStorePersistsAndClonesState(t *testing.T) {
	t.Parallel()

	store := NewStore(t.TempDir())
	locked, err := store.Lock()
	if err != nil {
		t.Fatalf("lock store: %v", err)
	}
	file := &File{
		Stacks: []Stack{{
			Name:   "delivery",
			Remote: "origin",
			Trunk:  "main",
			Branches: []Branch{{
				Name: "feature",
				Base: "base",
				Head: "head",
				PullRequest: &PullRequest{
					Number: 42,
					URL:    "https://example.test/pull/42",
				},
			}},
		}},
	}
	if err := locked.Save(file); err != nil {
		t.Fatalf("save state: %v", err)
	}
	if err := locked.Close(); err != nil {
		t.Fatalf("close store: %v", err)
	}

	locked, err = store.Lock()
	if err != nil {
		t.Fatalf("lock store again: %v", err)
	}
	defer func() {
		if closeErr := locked.Close(); closeErr != nil {
			t.Errorf("close store again: %v", closeErr)
		}
	}()
	loaded, err := locked.Load()
	if err != nil {
		t.Fatalf("load state: %v", err)
	}
	if loaded.Version != currentVersion {
		t.Fatalf("version = %d, want %d", loaded.Version, currentVersion)
	}
	if loaded.Stacks[0].Branches[0].PullRequest.Number != 42 {
		t.Fatalf("unexpected loaded state: %#v", loaded)
	}

	clone := CloneStack(loaded.Stacks[0])
	clone.Branches[0].PullRequest.Number = 99
	if loaded.Stacks[0].Branches[0].PullRequest.Number != 42 {
		t.Fatal("clone changed the original pull request")
	}
	if filepath.Base(store.Path()) != stateFileName {
		t.Fatalf("state path = %s", store.Path())
	}
	info, err := os.Stat(store.Path())
	if err != nil {
		t.Fatalf("stat state: %v", err)
	}
	if permissions := info.Mode().Perm(); permissions != 0o600 {
		t.Fatalf("state permissions = %o, want 600", permissions)
	}
	lockInfo, err := os.Stat(store.lockPath)
	if err != nil {
		t.Fatalf("stat state lock: %v", err)
	}
	if permissions := lockInfo.Mode().Perm(); permissions != 0o600 {
		t.Fatalf("state lock permissions = %o, want 600", permissions)
	}
}

func TestStoreLoadsMissingAndNormalizesEmptyState(t *testing.T) {
	t.Parallel()

	store := NewStore(t.TempDir())
	locked, err := store.Lock()
	if err != nil {
		t.Fatalf("lock store: %v", err)
	}
	defer func() {
		if closeErr := locked.Close(); closeErr != nil {
			t.Errorf("close store: %v", closeErr)
		}
	}()

	file, err := locked.Load()
	if err != nil {
		t.Fatalf("load missing state: %v", err)
	}
	if file.Version != currentVersion || file.Stacks == nil {
		t.Fatalf("unexpected missing state: %#v", file)
	}

	if err := os.WriteFile(store.Path(), []byte(`{"version":1}`), 0o600); err != nil {
		t.Fatalf("write empty state: %v", err)
	}
	file, err = locked.Load()
	if err != nil {
		t.Fatalf("load empty state: %v", err)
	}
	if file.Stacks == nil {
		t.Fatal("empty state retained a nil stack slice")
	}
}

func TestStoreRejectsInvalidAndNewerState(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name    string
		content string
		want    string
	}{
		{
			name:    "invalid JSON",
			content: "{",
			want:    "parsing state",
		},
		{
			name:    "newer version",
			content: `{"version":999,"stacks":[]}`,
			want:    "newer than supported",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()

			store := NewStore(t.TempDir())
			if err := os.WriteFile(
				store.Path(),
				[]byte(test.content),
				0o600,
			); err != nil {
				t.Fatalf("write state: %v", err)
			}
			locked, err := store.Lock()
			if err != nil {
				t.Fatalf("lock store: %v", err)
			}
			defer func() {
				_ = locked.Close()
			}()
			if _, err := locked.Load(); err == nil ||
				!strings.Contains(err.Error(), test.want) {
				t.Fatalf("load error = %v, want %q", err, test.want)
			}
		})
	}
}

func TestFileFindsStacksAndBranches(t *testing.T) {
	t.Parallel()

	file := &File{Stacks: []Stack{{
		Name: "delivery",
		Branches: []Branch{{
			Name: "feature",
		}},
	}}}
	if stack, exists := file.FindStack("delivery"); !exists ||
		stack.Name != "delivery" {
		t.Fatalf("FindStack() = %#v, %t", stack, exists)
	}
	if _, exists := file.FindStack("missing"); exists {
		t.Fatal("FindStack() found a missing stack")
	}
	if stack, exists := file.FindStackForBranch("feature"); !exists ||
		stack.Name != "delivery" {
		t.Fatalf("FindStackForBranch() = %#v, %t", stack, exists)
	}
	if _, exists := file.FindStackForBranch("missing"); exists {
		t.Fatal("FindStackForBranch() found a missing branch")
	}
}

func TestLockedStoreCloseAcceptsNilReceiver(t *testing.T) {
	t.Parallel()

	var locked *LockedStore
	if err := locked.Close(); err != nil {
		t.Fatalf("close nil store: %v", err)
	}
}
