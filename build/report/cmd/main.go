// Copyright 2022 The Android Open Source Project
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"log"
	"runtime"
	"strings"

	"tools/treble/build/report/app"
	"tools/treble/build/report/local"
	"tools/treble/build/report/report"
)

type repoFlags []app.ProjectCommit

func (r *repoFlags) Set(value string) error {
	commit := app.ProjectCommit{}
	items := strings.Split(value, ":")
	if len(items) > 2 {
		return (errors.New("Invalid repo value expected (proj:sha) format"))
	}
	commit.Project = items[0]
	if len(items) > 1 {
		commit.Revision = items[1]
	}
	*r = append(*r, commit)
	return nil
}
func (r *repoFlags) String() string {
	items := []string{}
	for _, fl := range *r {
		items = append(items, fmt.Sprintf("%s:%s", fl.Project, fl.Revision))
	}
	return strings.Join(items, " ")
}

var (
	// Common flags
	ninjaDbPtr     = flag.String("ninja", local.DefNinjaDb(), "Set the .ninja file to use when building metrics")
	ninjaExcPtr    = flag.String("ninja_cmd", local.DefNinjaExc(), "Set the ninja executable")
	manifestPtr    = flag.String("manifest", local.DefManifest(), "Set the location of the manifest file")
	repoBasePtr    = flag.String("repo_base", local.DefRepoBase(), "Set the repo base directory")
	workerCountPtr = flag.Int("worker_count", runtime.NumCPU(), "Number of worker routines")

	reportFlags  = flag.NewFlagSet("report", flag.ExitOnError)
	outputsFlags = flag.NewFlagSet("outputs", flag.ExitOnError)
)

func main() {
	ctx := context.Background()
	flag.Parse()

	subCmds := strings.Join([]string{"report", "outputs"}, " ")

	subArgs := flag.Args()
	if len(subArgs) < 1 {
		log.Fatalf("Expected a sub-command.  Possible sub-commands %s", subCmds)
	}
	log.SetFlags(log.LstdFlags | log.Llongfile)

	ninja := local.NewNinjaCli(*ninjaExcPtr, *ninjaDbPtr)
	rtx := &report.Context{
		RepoBase:    *repoBasePtr,
		Repo:        &report.RepoMan{},
		Build:       ninja,
		Project:     local.NewGitCli(),
		WorkerCount: *workerCountPtr}

	switch subArgs[0] {
	case "report":
		incHostToolPtr := reportFlags.Bool("host", false, "Include host tool metrics")
		hostToolPathPtr := reportFlags.String("hostbin", local.DefHostBinPath(), "Set the output directory for host tools")
		jsonPtr := reportFlags.Bool("json", false, "Print json data")
		verbosePtr := reportFlags.Bool("v", false, "Print verbose data")
		outputPtr := reportFlags.String("o", "", "Output to file")

		reportFlags.Parse(subArgs[1:])
		reportExc(ctx, rtx,
			&reportArgs{incHostTools: *incHostToolPtr, hostToolPath: *hostToolPathPtr,
				manifest: *manifestPtr, jsonOut: *jsonPtr, verbose: *verbosePtr,
				outFile: *outputPtr},
			reportFlags.Args())

	case "outputs":
		var commits repoFlags
		outputsFlags.Var(&commits, "repo", "Repo:SHA to build")
		buildPtr := outputsFlags.Bool("build", false, "Build outputs")
		outputPtr := outputsFlags.String("o", "", "Output to file")
		outputsFlags.Parse(subArgs[1:])
		outputsExc(ctx, rtx,
			&outputArgs{manifest: *manifestPtr, build: *buildPtr, builder: ninja, outputFile: *outputPtr},
			commits, outputsFlags.Args())

	default:
		log.Fatalf("Unknown sub-command <%s>.  Possible sub-commands %s", subCmds)
	}

}
