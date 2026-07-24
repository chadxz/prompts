package state

import (
	"path/filepath"
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
}
