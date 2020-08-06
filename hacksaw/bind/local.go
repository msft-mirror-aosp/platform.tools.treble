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

package bind

import (
	"fmt"
	"path"
	"syscall"

	"android.googlesource.com/platform/tools/treble.git/hacksaw/mount"
)

//localBinder executes PathBinder calls locally
type localBinder struct {
	mounter mount.Mounter
}

func NewLocalPathBinder() PathBinder {
	var p localBinder
	p.mounter = mount.NewSystemMounter()
	return &p
}

func NewFakePathBinder() PathBinder {
	var p localBinder
	p.mounter = mount.NewFakeMounter()
	return &p
}

func (p localBinder) checkValidPath(inPath string) error {
	for dir := path.Dir(inPath); dir != "." && dir != "/"; dir = path.Dir(dir) {
		// Only allow mounts in hacksaw path
		if path.Base(dir) == "hacksaw" {
			return nil
		}
	}
	return fmt.Errorf("Not allowed to bind mount path %s because it's outside a hacksaw workspace", inPath)
}

func (p localBinder) BindReadOnly(source string, destination string) error {
	// TODO: check valid path considering sym links
	err := p.mounter.Mount(source, destination,
		"bind", syscall.MS_BIND, "")
	if err != nil {
		return err
	}
	err = p.mounter.Mount(source, destination,
		"bind", syscall.MS_REMOUNT|syscall.MS_BIND|syscall.MS_RDONLY, "")
	return err
}

func (p localBinder) BindReadWrite(source string, destination string) error {
	// TODO: check valid path considering sym links
	err := p.mounter.Mount(source, destination,
		"bind", syscall.MS_BIND, "")
	return err
}

func (p localBinder) Unbind(destination string) error {
	// TODO: check valid path considering sym links
	err := p.mounter.Unmount(destination, syscall.MNT_DETACH)
	return err
}

func (p localBinder) List() ([]string, error) {
	return p.mounter.List()
}
