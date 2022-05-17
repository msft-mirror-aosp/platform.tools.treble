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
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"tools/treble/build/report/app"
)

//
// Repo and project related functions
//
type project struct {
	Name     string                    // Name
	RepoPath string                    // Path in repo
	GitProj  *app.GitProject           // Git project data
	ObjMap   map[string]app.GitTreeObj // Mapping of filename to git tree object
}

var unknownProject = &project{Name: "unknown", RepoPath: "unknown", GitProj: &app.GitProject{}}

// Repo containing a map of projects, this also contains a
// map between a source file and the project it belongs to
// allowing a quicker lookup of source file to project
type repo struct {
	RepoBase  string              // Absolute path to repo base
	ProjMap   map[string]*project // Map project name to project
	FileCache map[string]*project // map source files to project
}

// Create a mapping of projects from the input source manifest
func createProjectMap(ctx context.Context, manifest *app.RepoManifest, repoBase string, proj ProjectDependencies, getFiles bool) *repo {
	if !strings.HasSuffix(repoBase, "/") {
		repoBase += "/"
	}
	repo := &repo{RepoBase: repoBase}
	// Create map of remotes
	remotes := make(map[string]*app.RepoRemote)
	var defRemotePtr *app.RepoRemote
	for i, _ := range manifest.Remotes {
		remotes[manifest.Remotes[i].Name] = &manifest.Remotes[i]
	}

	defRemotePtr, exists := remotes[manifest.Default.Remote]
	if !exists {
		fmt.Printf("Failed to find default remote")
	}
	repo.FileCache = make(map[string]*project)
	repo.ProjMap = make(map[string]*project)
	for i, _ := range manifest.Projects {

		remotePtr := defRemotePtr
		if manifest.Projects[i].Remote != nil {
			remotePtr = remotes[*manifest.Projects[i].Remote]
		}
		proj := resolveProject(ctx, &manifest.Projects[i], remotePtr, proj, getFiles, &repo.FileCache)
		if proj != nil {
			// Add the remote information
			repo.ProjMap[proj.Name] = proj
		}
	}
	return repo
}

// Convert repo project to project with source files and revision
// information
func resolveProject(ctx context.Context, repoProj *app.RepoProject, remote *app.RepoRemote, proj ProjectDependencies, getFiles bool, fileCache *map[string]*project) *project {

	path := repoProj.Path
	if path == "" {
		path = repoProj.Name
	}
	gitDir := ""
	if strings.HasPrefix(path, "overlays/") {
		// Assume two levels of overlay path (overlay/XYZ)
		path = strings.Join(strings.Split(path, "/")[2:], "/")
		// The overlays .git symbolic links are not mapped correctly
		// into the jails.   Resolve them here, inside the nsjail the
		// absolute path for all git repos will be in the form of
		// /src/.git/
		symlink, _ := os.Readlink(filepath.Join(path, ".git"))
		parts := strings.Split(symlink, "/")
		repostart := 0
		for ; repostart < len(parts); repostart++ {
			if parts[repostart] != ".." {
				if repostart > 1 {
					repostart--
					parts[repostart] = "/src"
				}
				break
			}
		}
		gitDir = filepath.Join(parts[repostart:]...)

	}
	gitProj, err := proj.Project(ctx, path, gitDir, remote.Name, repoProj.Revision, getFiles)
	if err != nil {
		return nil
	}
	out := &project{Name: repoProj.Name, RepoPath: path, GitProj: gitProj}
	if len(gitProj.Files) > 0 {
		out.ObjMap = make(map[string]app.GitTreeObj)
		for _, obj := range gitProj.Files {
			(*fileCache)[filepath.Join(path, obj.Filename)] = out
			out.ObjMap[obj.Filename] = obj
		}
	}
	return out
}

// Get the build file for a given filename, this is a two step lookup.
// First find the project associated with the file via the file cache,
// then resolve the file via the project found.
//
// Most files will be relative paths from the repo workspace
func lookupProjectFile(ctx context.Context, repo *repo, filename *string) (*project, *app.BuildFile) {
	if proj, exists := repo.FileCache[*filename]; exists {
		repoName := (*filename)[len(proj.RepoPath)+1:]
		if gitObj, exists := proj.ObjMap[repoName]; exists {
			return proj, &app.BuildFile{Name: gitObj.Filename, Revision: gitObj.Sha}
		}
		return proj, nil
	} else {
		// Try resolving any symlinks
		if realpath, err := filepath.EvalSymlinks(*filename); err == nil {
			if realpath != *filename {
				return lookupProjectFile(ctx, repo, &realpath)
			}
		}

		if strings.HasPrefix(*filename, repo.RepoBase) {
			// Some dependencies pick up the full path try stripping out
			relpath := (*filename)[len(repo.RepoBase)+1:]
			return lookupProjectFile(ctx, repo, &relpath)
		}
	}
	return unknownProject, &app.BuildFile{Name: *filename, Revision: ""}
}

// Create a mapping of projects from the input source manifest
func resolveProjectMap(ctx context.Context, rtx *Context, manifestFile string, getFiles bool) chan *repo {
	outChan := make(chan *repo)
	go func() {
		defer close(outChan)
		// Parse the manifest file
		xmlRepo, err := rtx.Repo.Manifest(manifestFile)
		if err != nil {
			return
		}
		// Convert manifest into projects with source files
		repo := createProjectMap(ctx, xmlRepo, rtx.RepoBase, rtx.Project, getFiles)
		outChan <- repo
	}()
	return outChan
}
