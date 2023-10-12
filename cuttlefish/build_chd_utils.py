#!/usr/bin/python3
#
# Copyright (C) 2023 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.

import glob
import os
import shutil
import zipfile


def unzip_otatools(otatools_zip_path, output_dir):
  """Unzip otatools to a directory and set the permissions for execution.

  Args:
    otatools_zip_path: The path to otatools zip archive.
    output_dir: The root directory of the unzip output.
  """
  with zipfile.ZipFile(otatools_zip_path, 'r') as zf:
    zf.extractall(path=output_dir)

  for f in glob.glob(os.path.join(output_dir, 'bin', '*')):
    os.chmod(f, 0o777)


def _parse_copy_file_pair(copy_file_pair):
  """Convert a string to a source path and a destination path.

  Args:
    copy_file_pair: A string in the format of <src glob pattern>:<dst path>.

  Returns:
    The source path and the destination path.

  Raises:
    ValueError if the input string is in a wrong format.
  """
  split_pair = copy_file_pair.split(':', 1)
  if len(split_pair) != 2:
    raise ValueError(f'{copy_file_pair} is not a <src>:<dst> pair.')
  src_list = glob.glob(split_pair[0])
  if len(src_list) != 1:
    raise ValueError(f'{copy_file_pair} has more than one matched src files: '
                     f'{" ".join(src_list)}.')
  return src_list[0], split_pair[1]


def copy_files(copy_files_list, output_dir):
  """Copy files to the output directory.

  Args:
    copy_files_list: A list of copy file pairs, where a pair defines the src
                     glob pattern and the dst path.
    output_dir: The root directory of the copy dst.

  Raises:
    FileExistsError if the dst file already exists.
  """
  for pair in copy_files_list:
    src, dst = _parse_copy_file_pair(pair)
    # this line does not change dst if dst is absolute.
    dst = os.path.join(output_dir, dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    print(f'Copying {src} to {dst}')
    if os.path.exists(dst):
      raise FileExistsError(dst)
    shutil.copyfile(src, dst)
