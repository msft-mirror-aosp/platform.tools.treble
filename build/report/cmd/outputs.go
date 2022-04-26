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
	"encoding/json"
	"log"
	"os"

	"tools/treble/build/report/app"
	"tools/treble/build/report/report"
)

type response struct {
	Commits    *app.ProjectCommits   `json:"commits"`
	Query      *app.QueryRequest     `json:"query"`
	QueryRsp   *app.QueryResponse    `json:"query_result"`
	BuildFiles []*app.BuildCmdResult `json:"build_files"`
}

type Build interface {
	Build(ctx context.Context, target string) *app.BuildCmdResult
}
type outputArgs struct {
	manifest   string
	build      bool
	builder    Build
	outputFile string
}

func outputsExc(ctx context.Context, rtx *report.Context, args *outputArgs, commits repoFlags, files []string) {
	ret := response{}
	if len(commits) > 0 {
		log.Printf("Resolving %s", commits.String())
		ret.Commits = &app.ProjectCommits{ManifestFile: *manifestPtr, Commits: commits}
		commitFiles, err := report.ResolveCommits(ctx, rtx, ret.Commits)
		if err != nil {
			log.Fatalf("Failed to resolve commits %s", commits.String())
		}
		files = append(files, commitFiles...)
	}

	log.Printf("Querying  files %s \n", files)
	ret.Query = &app.QueryRequest{Files: files}
	var err error
	ret.QueryRsp, err = report.RunQuery(ctx, rtx, ret.Query)
	if err != nil {
		log.Fatalf("Failed to query outputs %s\n", err)
	}
	error := false
	if args.build {
		log.Println("Filtering output files")
		buildFiles := report.RunPathFilter(ctx, rtx, "droid", ret.QueryRsp.OutputFiles)
		for _, f := range buildFiles {
			log.Printf("Building %s\n", f)
			res := args.builder.Build(ctx, f)
			log.Printf("%s\n", res.Output)
			if res.Success != true {
				error = true
			}
			ret.BuildFiles = append(ret.BuildFiles, res)
		}
	}

	b, _ := json.MarshalIndent(ret, "", "\t")
	if args.outputFile == "" {
		os.Stdout.Write(b)
	} else {
		os.WriteFile(args.outputFile, b, 0644)
	}

	if error {
		log.Fatal("Failed to build outputs")
	}
}
