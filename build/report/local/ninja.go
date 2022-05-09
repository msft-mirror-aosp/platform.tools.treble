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

package local

import (
	"bufio"
	"bytes"
	"context"
	"io"
	"io/ioutil"
	"strings"
	"time"

	"tools/treble/build/report/app"
)

// Separate out the executable to allow tests to override the results
type ninjaExec interface {
	Command(ctx context.Context, target string) (*bytes.Buffer, error)
	Input(ctx context.Context, target string) (*bytes.Buffer, error)
	Query(ctx context.Context, target string) (*bytes.Buffer, error)
	Path(ctx context.Context, target string, dependency string) (*bytes.Buffer, error)
	Paths(ctx context.Context, target string, dependency string) (*bytes.Buffer, error)
	Build(ctx context.Context, target string) (*bytes.Buffer, error)
}

// Parse data

// Add all lines to a given array removing any leading whitespace
func linesToArray(s *bufio.Scanner, arr *[]string) {
	for s.Scan() {
		line := strings.TrimSpace(s.Text())
		*arr = append(*arr, line)
	}
}

// parse -t commands
func parseCommand(target string, data *bytes.Buffer) (*app.BuildCommand, error) {
	out := &app.BuildCommand{Target: target, Cmds: []string{}}
	s := bufio.NewScanner(data)
	// This tool returns all the commands needed to build a target.
	// When running against a target like droid the default capacity
	// will be overrun.   Extend the capacity here.
	const capacity = 1024 * 1024
	buf := make([]byte, capacity)
	s.Buffer(buf, capacity)
	linesToArray(s, &out.Cmds)
	return out, nil
}

// parse -t inputs
func parseInput(target string, data *bytes.Buffer) (*app.BuildInput, error) {
	out := &app.BuildInput{Target: target, Files: []string{}}
	s := bufio.NewScanner(data)
	linesToArray(s, &out.Files)
	return out, nil
}

// parse -t query
func parseQuery(target string, data *bytes.Buffer) (*app.BuildQuery, error) {
	out := &app.BuildQuery{Target: target, Inputs: []string{}, Outputs: []string{}}
	const (
		unknown = iota
		inputs
		outputs
	)
	state := unknown
	s := bufio.NewScanner(data)
	for s.Scan() {
		line := strings.TrimSpace(s.Text())
		if strings.HasPrefix(line, "input:") {
			state = inputs
		} else if strings.HasPrefix(line, "outputs:") {
			state = outputs
		} else {
			switch state {
			case inputs:
				out.Inputs = append(out.Inputs, line)
			case outputs:
				out.Outputs = append(out.Outputs, line)
			}
		}
	}
	return out, nil
}

// parse -t path
func parsePath(target string, dependency string, data *bytes.Buffer) (*app.BuildPath, error) {
	out := &app.BuildPath{Target: target, Dependency: dependency, Paths: []string{}}
	s := bufio.NewScanner(data)
	linesToArray(s, &out.Paths)
	return out, nil
}

// parse -t paths
func parsePaths(target string, dependency string, data *bytes.Buffer) ([]*app.BuildPath, error) {
	out := []*app.BuildPath{}
	s := bufio.NewScanner(data)
	for s.Scan() {
		path := strings.Fields(s.Text())
		out = append(out, &app.BuildPath{Target: target, Dependency: dependency, Paths: path})
	}
	return out, nil
}

// parse build output
func parseBuild(target string, data *bytes.Buffer, success bool) *app.BuildCmdResult {
	out := &app.BuildCmdResult{Name: target, Output: []string{}}
	s := bufio.NewScanner(data)
	out.Success = success
	linesToArray(s, &out.Output)
	return out
}

//
// Command line interface to ninja binary.
//
// This file implements the ninja.Ninja interface by querying
// the build graph via the ninja binary.  The mapping between
// the interface and the binary are as follows:
//    Command()   -t commands
//    Input()     -t inputs
//    Query()     -t query
//    Path()      -t path
//    Paths()     -t paths
//
//

type ninjaCmd struct {
	cmd string
	db  string

	timeout      time.Duration
	buildTimeout time.Duration
}

func (n *ninjaCmd) runTool(ctx context.Context, tool string, targets []string) (out *bytes.Buffer, err error) {
	args := append([]string{
		"-f", n.db,
		"-t", tool}, targets...)
	data := []byte{}
	err, _ = runPipe(ctx, n.timeout, n.cmd, args, func(r io.Reader) {
		data, _ = ioutil.ReadAll(r)
	})
	return bytes.NewBuffer(data), err

}
func (n *ninjaCmd) Command(ctx context.Context, target string) (*bytes.Buffer, error) {
	return n.runTool(ctx, "commands", []string{target})
}
func (n *ninjaCmd) Input(ctx context.Context, target string) (*bytes.Buffer, error) {
	return n.runTool(ctx, "inputs", []string{target})
}
func (n *ninjaCmd) Query(ctx context.Context, target string) (*bytes.Buffer, error) {
	return n.runTool(ctx, "query", []string{target})
}
func (n *ninjaCmd) Path(ctx context.Context, target string, dependency string) (*bytes.Buffer, error) {
	return n.runTool(ctx, "path", []string{target, dependency})
}
func (n *ninjaCmd) Paths(ctx context.Context, target string, dependency string) (*bytes.Buffer, error) {
	return n.runTool(ctx, "paths", []string{target, dependency})
}
func (n *ninjaCmd) Build(ctx context.Context, target string) (*bytes.Buffer, error) {

	args := append([]string{
		"-f", n.db,
		target})
	data := []byte{}
	err, _ := runPipe(ctx, n.buildTimeout, n.cmd, args, func(r io.Reader) {
		data, _ = ioutil.ReadAll(r)
	})

	return bytes.NewBuffer(data), err
}

type ninjaCli struct {
	n ninjaExec
}

// ninja -t commands
func (cli *ninjaCli) Command(ctx context.Context, target string) (*app.BuildCommand, error) {
	raw, err := cli.n.Command(ctx, target)
	if err != nil {
		return nil, err
	}
	return parseCommand(target, raw)
}

// ninja -t inputs
func (cli *ninjaCli) Input(ctx context.Context, target string) (*app.BuildInput, error) {
	raw, err := cli.n.Input(ctx, target)
	if err != nil {
		return nil, err
	}
	return parseInput(target, raw)
}

// ninja -t query
func (cli *ninjaCli) Query(ctx context.Context, target string) (*app.BuildQuery, error) {
	raw, err := cli.n.Query(ctx, target)
	if err != nil {
		return nil, err
	}
	return parseQuery(target, raw)
}

// ninja -t path
func (cli *ninjaCli) Path(ctx context.Context, target string, dependency string) (*app.BuildPath, error) {
	raw, err := cli.n.Path(ctx, target, dependency)
	if err != nil {
		return nil, err
	}
	return parsePath(target, dependency, raw)
}

// ninja -t paths
func (cli *ninjaCli) Paths(ctx context.Context, target string, dependency string) ([]*app.BuildPath, error) {
	raw, err := cli.n.Paths(ctx, target, dependency)
	if err != nil {
		return nil, err
	}
	return parsePaths(target, dependency, raw)
}

// Build given target
func (cli *ninjaCli) Build(ctx context.Context, target string) *app.BuildCmdResult {
	raw, err := cli.n.Build(ctx, target)
	return parseBuild(target, raw, err == nil)

}
func NewNinjaCli(cmd string, db string) *ninjaCli {
	cli := &ninjaCli{n: &ninjaCmd{cmd: cmd, db: db, timeout: 100000 * time.Millisecond, buildTimeout: 300000 * time.Millisecond}}
	return (cli)
}
