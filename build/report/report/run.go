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

package report

import (
	"context"
	"errors"
	"fmt"
	"io/fs"
	"path/filepath"

	"tools/treble/build/report/app"
)

// Find all binary executables under the given directory along with the number
// of symlinks
//
func binaryExecutables(ctx context.Context, dir string, recursive bool) ([]string, int, error) {
	var files []string
	numSymLinks := 0
	err := filepath.WalkDir(dir, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if !d.IsDir() {
			if info, err := d.Info(); err == nil {
				if info.Mode()&0111 != 0 {
					files = append(files, path)
				}
				if d.Type()&fs.ModeSymlink != 0 {
					numSymLinks++
				}
			}
		} else {
			if !recursive {
				if path != dir {
					return filepath.SkipDir
				}
			}
		}
		return nil
	})

	return files, numSymLinks, err
}

// Run reports

//
// Run report request
//
// Setup routines to:
//    - resolve the manifest projects
//    - resolve build queries
//
// Once the manifest projects have been resolved the build
// queries can be fully resolved
//
func RunReport(ctx context.Context, rtx *Context, req *app.ReportRequest) (*app.Report, error) {

	repoCh := resolveProjectMap(ctx, rtx, req.ManifestFile, true)
	inChan, targetCh := targetResolvers(ctx, rtx)
	hostTargetSymLinks := 0
	hostTargetMap := make(map[string]bool)
	go func() {
		for i, _ := range req.Targets {
			inChan <- req.Targets[i]
		}

		if req.IncludeHostTools {
			hostTargets, symLinks, _ := binaryExecutables(ctx, req.HostToolPath, true)
			hostTargetSymLinks = symLinks
			for i, _ := range hostTargets {
				inChan <- hostTargets[i]
				hostTargetMap[hostTargets[i]] = true
			}
		}
		close(inChan)
	}()
	// Wait for repo projects to be resolved
	repo := <-repoCh

	// Resolve the build inputs into build target projects
	buildTargetChan := resolveBuildInputs(ctx, rtx, repo, targetCh)

	out := &app.Report{}
	if req.IncludeHostTools {
		out.Host = &app.HostReport{Path: req.HostToolPath, SymLinks: hostTargetSymLinks}
	}
	for bt := range buildTargetChan {
		if _, exists := hostTargetMap[bt.Name]; exists {
			out.Host.Targets = append(out.Host.Targets, bt)
		} else {
			out.Targets = append(out.Targets, bt)
		}
	}

	return out, nil
}

// Resolve set of commits into set of files
func ResolveCommits(ctx context.Context, rtx *Context, req *app.ProjectCommits) ([]string, error) {
	// Resolve project map, don't need the repo files here
	repo := <-resolveProjectMap(ctx, rtx, req.ManifestFile, false)

	files := []string{}
	// Resolve any commits
	for _, commit := range req.Commits {
		if proj, exists := repo.ProjMap[commit.Project]; exists {
			info, err := rtx.Project.CommitInfo(ctx, proj.GitProj, commit.Revision)
			if err == nil {
				for _, f := range info.Files {
					if f.Type != app.GitFileRemoved {
						files = append(files, filepath.Join(proj.RepoPath, f.Filename))
					}
				}
			}
		} else {
			return nil, errors.New(fmt.Sprintf("Failed to find commit %s:%s", commit.Project, commit.Revision))
		}
	}
	return files, nil

}

// Run query report based on the input request.
//
// For each input file query the target and
// create a set of the inputs and outputs associated
// with all the input files.
//
//
func RunQuery(ctx context.Context, rtx *Context, req *app.QueryRequest) (*app.QueryResponse, error) {
	inChan, queryCh := queryResolvers(ctx, rtx)

	go func() {
		// Convert source files to outputs
		for _, target := range req.Files {
			inChan <- target
		}
		close(inChan)
	}()

	inFiles := make(map[string]bool)
	outFiles := make(map[string]bool)
	unknownSrcFiles := make(map[string]bool)
	for result := range queryCh {
		if result.error {
			unknownSrcFiles[result.source] = true
		} else {
			for _, outFile := range result.query.Outputs {
				outFiles[outFile] = true
			}
			for _, inFile := range result.query.Inputs {
				inFiles[inFile] = true
			}

		}
	}

	out := &app.QueryResponse{}
	for k, _ := range outFiles {
		out.OutputFiles = append(out.OutputFiles, k)
	}
	for k, _ := range inFiles {
		out.InputFiles = append(out.InputFiles, k)
	}
	for k, _ := range unknownSrcFiles {
		out.UnknownFiles = append(out.UnknownFiles, k)
	}

	return out, nil
}

// Check if path exists between target and outputs provided, return outputs that have a
// path to target.  Only return valid paths via the output any errors are dropped
func RunPathFilter(ctx context.Context, rtx *Context, target string, outputs []string) []string {
	var filter []string
	inChan, pathCh := pathResolvers(ctx, rtx, target)
	// Convert source files to outputs
	go func() {
		for _, out := range outputs {
			inChan <- out
		}
		close(inChan)
	}()
	for result := range pathCh {
		if !result.error {
			filter = append(filter, result.filename)
		}
	}
	return filter
}

func RunPaths(ctx context.Context, rtx *Context, target string, files []string) []*app.BuildPath {
	out := []*app.BuildPath{}
	inChan, pathCh := pathsResolvers(ctx, rtx, target)
	// Convert source files to outputs
	go func() {
		for _, f := range files {
			inChan <- f
		}
		close(inChan)
	}()

	for result := range pathCh {
		if !result.error {
			out = append(out, result.path)
		}
	}
	return out

}
