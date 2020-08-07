// Copyright 2020 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// hacksaw let's you create lightweight workspaces of large codebases
package main

import (
	"fmt"
	"os"
	"os/user"
	"path/filepath"

	"android.googlesource.com/platform/tools/treble.git/hacksaw/bind"
	"android.googlesource.com/platform/tools/treble.git/hacksaw/client"
)

func getPathBinder() bind.PathBinder {
	var pathBinder bind.PathBinder
	uid := os.Geteuid()
	if uid == 0 {
		pathBinder = bind.NewLocalPathBinder()
	} else {
		pathBinder = bind.NewRemoteBindClient("/var/run/hacksaw.sock")
	}
	return pathBinder
}

func getWorkspaceTopDir() (string, error) {
	var home string
	var err error
	uid := os.Geteuid()
	sudoUser := os.Getenv("SUDO_USER")
	if uid == 0 && sudoUser != "" {
		usr, err := user.Lookup(sudoUser)
		if err != nil {
			return "", err
		}
		home = usr.HomeDir
	} else {
		home, err = os.UserHomeDir()
		if err != nil {
			return "", err
		}
	}
	// The hacksaw mount daemon requires all mounts
	// to be contained in a directory named "hacksaw"
	return filepath.EvalSymlinks(filepath.Join(home, "hacksaw"))
}

func run() error {
	workspaceTopDir, err := getWorkspaceTopDir()
	if err != nil {
		return err
	}
	pathBinder := getPathBinder()
	return client.HandleCommand(workspaceTopDir, pathBinder, os.Args)
}

func main() {
	if err := run(); err != nil {
		fmt.Println("Error:", err)
		os.Exit(1)
	}
}
