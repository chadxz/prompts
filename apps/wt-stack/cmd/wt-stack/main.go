package main

import (
	"os"

	"github.com/chadxz/prompts/apps/wt-stack/internal/cli"
)

func main() {
	os.Exit(cli.Execute())
}
