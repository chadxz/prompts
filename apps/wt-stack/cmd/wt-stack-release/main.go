package main

import (
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"time"

	"github.com/chadxz/prompts/apps/wt-stack/internal/release"
)

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr, time.Now()))
}

func run(
	args []string,
	out io.Writer,
	errOut io.Writer,
	now time.Time,
) int {
	flags := flag.NewFlagSet("wt-stack-release", flag.ContinueOnError)
	flags.SetOutput(errOut)
	changelog := flags.String(
		"changelog",
		"CHANGELOG.md",
		"path to the wt-stack changelog",
	)
	currentVersion := flags.String(
		"current-version",
		"",
		"latest released semantic version",
	)
	date := flags.String(
		"date",
		now.Format("2006-01-02"),
		"release date in YYYY-MM-DD form",
	)
	if err := flags.Parse(args); err != nil {
		return 1
	}
	if flags.NArg() != 0 {
		_, _ = fmt.Fprintln(errOut, "unexpected positional arguments")
		return 1
	}
	if *currentVersion == "" {
		_, _ = fmt.Fprintln(errOut, "--current-version is required")
		return 1
	}
	releaseDate, err := time.Parse("2006-01-02", *date)
	if err != nil {
		_, _ = fmt.Fprintf(errOut, "parsing release date: %v\n", err)
		return 1
	}
	info, err := os.Stat(*changelog)
	if err != nil {
		_, _ = fmt.Fprintf(errOut, "reading changelog metadata: %v\n", err)
		return 1
	}
	content, err := os.ReadFile(*changelog)
	if err != nil {
		_, _ = fmt.Fprintf(errOut, "reading changelog: %v\n", err)
		return 1
	}
	result, err := release.Prepare(content, *currentVersion, releaseDate)
	if errors.Is(err, release.ErrNoChanges) {
		_, _ = fmt.Fprintln(out, "release=false")
		return 0
	}
	if err != nil {
		_, _ = fmt.Fprintf(errOut, "preparing release: %v\n", err)
		return 1
	}
	if err := os.WriteFile(
		*changelog,
		result.Content,
		info.Mode().Perm(),
	); err != nil {
		_, _ = fmt.Fprintf(errOut, "writing changelog: %v\n", err)
		return 1
	}
	_, _ = fmt.Fprintln(out, "release=true")
	_, _ = fmt.Fprintf(out, "version=%s\n", result.Version)
	_, _ = fmt.Fprintf(out, "bump=%s\n", result.Bump)
	return 0
}
