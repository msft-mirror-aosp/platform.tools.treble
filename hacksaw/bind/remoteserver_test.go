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
	"reflect"
	"testing"
)

func TestServerBind(t *testing.T) {
	fakeBinder := NewFakePathBinder()
	server := NewServer(fakeBinder)
	bindROArgs := BindReadOnlyArgs{
		Source:      "/path/to/readonly/source",
		Destination: "/path/to/hacksaw/readonly/destination",
	}
	var bindROReply BindReadOnlyReply
	if err := server.BindReadOnly(&bindROArgs, &bindROReply); err != nil {
		t.Error(err)
	}
	if bindROReply.Err != "" {
		t.Error(bindROReply.Err)
	}
	bindRWArgs := BindReadWriteArgs{
		Source:      "/path/to/readwrite/source",
		Destination: "/path/to/hacksaw/readwrite/destination",
	}
	var bindRWReply BindReadWriteReply
	if err := server.BindReadWrite(&bindRWArgs, &bindRWReply); err != nil {
		t.Error(err)
	}
	if bindRWReply.Err != "" {
		t.Error(bindRWReply.Err)
	}
	var listArgs ListArgs
	var listReply ListReply
	err := server.List(&listArgs, &listReply)
	if err != nil {
		t.Error(err)
	}
	if listReply.Err != "" {
		t.Error(listReply.Err)
	}
	expectedList := []string{
		"/path/to/hacksaw/readonly/destination",
		"/path/to/hacksaw/readwrite/destination",
	}
	if !reflect.DeepEqual(listReply.BindList, expectedList) {
		t.Errorf("Bind list %v is different than expected bind %v",
			listReply.BindList, expectedList)
	}
	unbindArgs := UnbindArgs{
		Destination: "/path/to/hacksaw/readwrite/destination",
	}
	var unbindReply UnbindReply
	if err := server.Unbind(&unbindArgs, &unbindReply); err != nil {
		t.Error(err)
	}
	if unbindReply.Err != "" {
		t.Error(unbindReply.Err)
	}
	err = server.List(&listArgs, &listReply)
	if err != nil {
		t.Error(err)
	}
	if listReply.Err != "" {
		t.Error(listReply.Err)
	}
	expectedList = []string{
		"/path/to/hacksaw/readonly/destination",
	}
	if !reflect.DeepEqual(listReply.BindList, expectedList) {
		t.Errorf("Bind list %v is different than expected bind %v",
			listReply.BindList, expectedList)
	}
}
