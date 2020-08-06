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

package file

import (
	"fmt"
	"os"
	"os/user"
	"path/filepath"
	"strconv"
)

func changeOwner(name string) error {
	uid := os.Geteuid()
	sudoUser := os.Getenv("SUDO_USER")
	if uid != 0 || sudoUser == "" {
		return nil
	}
	usr, err := user.Lookup(sudoUser)
	if err != nil {
		return err
	}
	sudoUid, err := strconv.Atoi(usr.Uid)
	if err != nil {
		return err
	}
	sudoGid, err := strconv.Atoi(usr.Gid)
	if err != nil {
		return err
	}
	err = os.Lchown(name, sudoUid, sudoGid)
	return err
}

func Symlink(oldname, newname string) error {
	err := os.Symlink(oldname, newname)
	if err != nil {
		return err
	}
	return changeOwner(newname)
}

func Mkdir(name string, perm os.FileMode) error {
	if err := os.Mkdir(name, perm); err != nil {
		return err
	}
	return changeOwner(name)
}

func MkdirAll(name string, perm os.FileMode) error {
	name, err := filepath.Abs(name)
	if err != nil {
		return err
	}
	//Create list of directory ancestors from topmost
	//to bottommost
	var dirAncestry []string
	for dir := name; dir != "/"; dir = filepath.Dir(dir) {
		dirAncestry = append([]string{dir}, dirAncestry...)
	}
	for _, dir := range dirAncestry {
		stat, err := os.Stat(dir)
		if err == nil {
			if stat.IsDir() {
				continue
			} else {
				return fmt.Errorf(dir, "exists and is not a directory")
			}
		} else if os.IsNotExist(err) {
			err = Mkdir(dir, perm)
			if err != nil {
				return err
			}
		} else {
			return err
		}
	}
	return nil
}

func Create(name string) (*os.File, error) {
	createdFile, err := os.Create(name)
	if err != nil {
		return createdFile, err
	}

	uid := os.Geteuid()
	sudoUser := os.Getenv("SUDO_USER")
	if uid != 0 || sudoUser == "" {
		return createdFile, nil
	}
	usr, err := user.Lookup(sudoUser)
	if err != nil {
		return createdFile, err
	}
	sudoUid, err := strconv.Atoi(usr.Uid)
	if err != nil {
		return createdFile, err
	}
	sudoGid, err := strconv.Atoi(usr.Gid)
	if err != nil {
		return createdFile, err
	}
	err = createdFile.Chown(sudoUid, sudoGid)
	return createdFile, err
}
