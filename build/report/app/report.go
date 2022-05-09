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

package app

// Report request structure
type ReportRequest struct {
	IncludeHostTools bool     `json:"include_host_tools"` // Get target information for all host tools found
	HostToolPath     string   `json:"host_tool_path"`     // Location of output host tools
	ManifestFile     string   `json:"manifest"`           // Repo manifest file
	Targets          []string `json:"targets"`            // Targets
}

// Host tool report response data
type HostReport struct {
	Path     string         `json:"path"`      // Path to find host tools
	SymLinks int            `json:"sym_links"` // Number of symlinks found
	Targets  []*BuildTarget `json:"targets"`   // Build targets for tools found
}

// Report response data
type Report struct {
	Host    *HostReport    `json:"host"`    // Host response
	Targets []*BuildTarget `json:"targets"` // Build target data
}

// Project level commit
type ProjectCommit struct {
	Project  string `json:"project"`  // Project
	Revision string `json:"revision"` // Revision
}

// Project level commits
type ProjectCommits struct {
	ManifestFile string          `json:"manifest"` // Repo manifest file
	Commits      []ProjectCommit `json:"commits"`  // Commits to resolve
}

// Query request
type QueryRequest struct {
	Files []string `json:"files"` // Files to resolve
}

// Output response
type QueryResponse struct {
	InputFiles   []string `json:"input_files"`             // Input files found
	OutputFiles  []string `json:"output_files"`            // Output files found
	UnknownFiles []string `json:"unknown_files,omitempty"` // Unknown files
}
