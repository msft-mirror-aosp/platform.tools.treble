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
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"

	"tools/treble/build/report/app"
	"tools/treble/build/report/report"
)

type reportArgs struct {
	incHostTools bool
	hostToolPath string
	manifest     string
	jsonOut      bool
	verbose      bool
	outFile      string
}

func reportExc(ctx context.Context, rtx *report.Context, args *reportArgs, targets []string) {
	req := &app.ReportRequest{IncludeHostTools: args.incHostTools,
		HostToolPath: args.hostToolPath,
		ManifestFile: args.manifest,
		Targets:      targets}

	out, err := report.RunReport(ctx, rtx, req)

	if err != nil {
		log.Fatalf("Failed to run report : %s\n", err)
	}
	if args.jsonOut {
		b, _ := json.MarshalIndent(out, "", "\t")
		if args.outFile == "" {
			os.Stdout.Write(b)
		} else {
			os.WriteFile(args.outFile, b, 0644)
		}
	} else {
		if args.outFile == "" {
			printTextReport(os.Stdout, out, args.verbose)
		} else {
			file, err := os.Create(args.outFile)
			if err != nil {
				log.Fatalf("Failed to create output file %s (%s)", args.outFile, err)
			}
			w := bufio.NewWriter(file)
			printTextReport(w, out, args.verbose)
		}
	}

}

func printTextReport(w io.Writer, report *app.Report, verbose bool) {
	fmt.Fprintln(w, "Metric Report")
	if report.Host != nil {
		// Get the unique number of inputs
		hostSourceFileMap := make(map[string]bool)
		hostSourceProjectMap := make(map[string]bool)
		for i, _ := range report.Host.Targets {
			for j, _ := range report.Host.Targets[i].Projects {
				hostSourceProjectMap[report.Host.Targets[i].Projects[j].Name] = true
				for k, _ := range report.Host.Targets[i].Projects[j].Files {
					hostSourceFileMap[filepath.Join(report.Host.Targets[i].Projects[j].Path,
						report.Host.Targets[i].Projects[j].Files[k].Name)] = true
				}
			}
		}
		fmt.Fprintln(w, "  Host Tools")
		fmt.Fprintf(w, "      %-20s       : %s\n", "Directory", report.Host.Path)
		fmt.Fprintf(w, "         %-20s    : %d\n", "Tools", len(report.Host.Targets))
		fmt.Fprintf(w, "         %-20s    : %d\n", "Prebuilts", report.Host.SymLinks)
		fmt.Fprintf(w, "         %-20s    : %d\n", "Inputs", len(hostSourceFileMap))
		fmt.Fprintf(w, "         %-20s    : %d\n", "Projects", len(hostSourceProjectMap))

		if verbose {
			for proj, _ := range hostSourceProjectMap {
				fmt.Fprintf(w, "            %s\n", proj)
			}
		}
	}
	if len(report.Targets) != 0 {
		fmt.Fprintln(w, "  Targets")
		for i, _ := range report.Targets {
			fmt.Fprintf(w, "      %-20s       : %s\n", "Name", report.Targets[i].Name)
			fmt.Fprintf(w, "         %-20s    : %d\n", "Build Steps", report.Targets[i].Steps)
			fmt.Fprintf(w, "         %-20s        \n", "Inputs")
			fmt.Fprintf(w, "            %-20s : %d\n", "Files", report.Targets[i].FileCount)
			fmt.Fprintf(w, "            %-20s : %d\n", "Projects", len(report.Targets[i].Projects))
			fmt.Fprintln(w)
			for _, proj := range report.Targets[i].Projects {
				fmt.Fprintf(w, "            %-120s : %d\n", proj.Name, len(proj.Files))
				if verbose {
					for _, file := range proj.Files {
						fmt.Fprintf(w, "               %-20s : %s\n", file.Revision, file.Name)
					}
				}
			}

		}

	}
}
