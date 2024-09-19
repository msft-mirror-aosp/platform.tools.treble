#!/usr/bin/python3
#
# Copyright (C) 2024 The Android Open Source Project
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

import argparse
import dataclasses
import os
import shlex
import subprocess
import tempfile
from typing import List

from build_chd_utils import copy_files, unzip_otatools

"""Builds a vendor_boot-chd_debug.img.

The vendor_boot-chd_debug.img is built by adding those CHD specific debugging
files to a Cuttlefish's vendor_boot-debug.img, using a new ramdisk fragment.

Test command:
python3 tools/treble/cuttlefish/build_chd_debug_ramdisk.py \
    $ANDROID_PRODUCT_OUT/vendor_boot-debug.img \
    -o $ANDROID_PRODUCT_OUT/vendor_boot-chd_debug.img \
    --otatools_zip $ANDROID_PRODUCT_OUT/otatools.zip \
    --add_file chd_debug.prop:adb_debug.prop
"""

# The value of ramdisk type needs to be synchronized with
# `system/tools/mkbootimg/mkbootimg.py`. We choose `_PLATFORM` here because the
# CHD debug ramdisk will be used in normal boot (not for _RECOVERY or _DLKM).
_VENDOR_RAMDISK_TYPE_PLATFORM = '1'


def _parse_args() -> argparse.Namespace:
  """Parse the arguments for building the chd debug ramdisk.

  Returns:
    An object of the parsed arguments.
  """
  parser = argparse.ArgumentParser()
  parser.add_argument('input_img',
                      help='The input Cuttlefish vendor boot debug image.')
  parser.add_argument('--output_img', '-o', required=True,
                      help='The output CHD vendor boot debug image.')
  parser.add_argument('--otatools_zip', required=True,
                      help='Path to the otatools.zip.')
  parser.add_argument('--add_file', action='append', default=[],
                      help='The file to be added to the CHD debug ramdisk. '
                           'The format is <src path>:<dst path>.')
  return parser.parse_args()


@dataclasses.dataclass
class ImageOptions:
  """The options for building the CHD vendor boot debug image.

  Attributes:
    input_image: path of the input vendor boot debug image.
    output_image: path of the output CHD vendor boot debug image.
    otatools_dir: path of the otatools directory.
    temp_dir: path of the temporary directory for ramdisk filesystem.
    files_to_add: a list of files to be added in the debug ramdisk, where a
      pair defines the src and dst path of each file.
  """
  input_image: str
  output_image: str
  otatools_dir: str
  temp_dir: str
  files_to_add: List[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class BootImage:
  """Provide some functions to modify a boot image.

  Attributes:
    bootimg: path of the input boot image to be modified.
    bootimg_dir: path of a temporary directory that would be used to extract
      the input boot image.
    unpack_bootimg_bin: path of the `unpack_bootimg` executable.
    mkbootfs_bin: path of the `mkbootfs` executable.
    mkbootimg_bin: path of the `mkbootimg` executable.
    lz4_bin: path of the `lz4` executable.
    bootimg_args: the arguments that were used to build this boot image.
  """
  bootimg: str
  bootimg_dir: str
  unpack_bootimg_bin: str
  mkbootfs_bin: str
  mkbootimg_bin: str
  lz4_bin: str
  bootimg_args: List[str] = dataclasses.field(default_factory=list)

  def unpack(self) -> None:
    """Unpack the boot.img and capture the bootimg arguments."""
    if self.bootimg_args:
      raise RuntimeError(f'cannot unpack {self.bootimg} twice')
    print(f'Unpacking {self.bootimg} to {self.bootimg_dir}')
    unpack_cmd = [
        self.unpack_bootimg_bin,
        '--boot_img', self.bootimg,
        '--out', self.bootimg_dir,
        '--format', 'mkbootimg'
    ]
    unpack_result = subprocess.run(unpack_cmd, check=True,
                                   capture_output=True, encoding='utf-8')
    self.bootimg_args = shlex.split(unpack_result.stdout)

  def add_ramdisk(self, ramdisk_root: str) -> None:
    """Add a new ramdisk fragment and update the bootimg arguments.

    Args:
      ramdisk_root: path of the root directory which contains the content of
        the new ramdisk fragment.
    """
    # Name the new ramdisk using the smallest unused index.
    ramdisk_files = [file for file in os.listdir(self.bootimg_dir)
                     if file.startswith('vendor_ramdisk')]
    new_ramdisk_name = f'vendor_ramdisk{len(ramdisk_files):02d}'
    new_ramdisk_file = os.path.join(self.bootimg_dir, new_ramdisk_name)
    if os.path.exists(new_ramdisk_file):
      raise FileExistsError(f'{new_ramdisk_file} already exists')

    print(f'Adding a new vendor ramdisk fragment {new_ramdisk_file}')
    mkbootfs_cmd = [self.mkbootfs_bin, ramdisk_root]
    mkbootfs_result = subprocess.run(mkbootfs_cmd, check=True,
                                     capture_output=True)

    compress_cmd = [self.lz4_bin, '-l', '-12', '--favor-decSpeed']
    with open(new_ramdisk_file, 'w') as o:
      subprocess.run(compress_cmd, check=True,
                     input=mkbootfs_result.stdout, stdout=o)

    # Update the bootimg arguments to include the new ramdisk file.
    self.bootimg_args.extend([
        '--ramdisk_type', _VENDOR_RAMDISK_TYPE_PLATFORM,
        '--ramdisk_name', 'chd',
        '--vendor_ramdisk_fragment', new_ramdisk_file
    ])

  def pack(self, output_img: str) -> None:
    """Pack the boot.img using `self.bootimg_args`.

    Args:
      output_img: path of the output boot image.
    """
    print(f'Packing {output_img} with args: {self.bootimg_args}')
    mkbootimg_cmd = [
        self.mkbootimg_bin, '--vendor_boot', output_img
    ] + self.bootimg_args
    subprocess.check_call(mkbootimg_cmd)


def _prepare_env(otatools_dir: str) -> List[str]:
  """Get the executable path of the required otatools.

  We need `unpack_bootimg`, `mkbootfs`, `mkbootimg` and `lz4` for building CHD
  debug ramdisk. This function returns the path to the above tools in order.

  Args:
    otatools_dir: path of the otatools directory.

  Raises:
    FileNotFoundError if any required otatool does not exist.
  """
  tools_path = []
  for tool_name in ['unpack_bootimg', 'mkbootfs', 'mkbootimg', 'lz4']:
    tool_path = os.path.join(otatools_dir, 'bin', tool_name)
    if not os.path.exists(tool_path):
      raise FileNotFoundError(f'otatool {tool_path} does not exist')
    tools_path.append(tool_path)
  return tools_path


def add_debug_ramdisk_files(options: ImageOptions) -> None:
  """Add files to a vendor boot debug image.

  This function creates a new ramdisk fragment, add this fragment into the
  input vendor boot debug image, and generate an output image.

  Args:
    options: a `ImageOptions` object which specifies the options for building
      a CHD vendor boot debug image.

  Raises:
    FileExistsError if having duplicated ramdisk fragments.
    FileNotFoundError if any required otatool does not exist.
  """
  print(f'Adding {options.files_to_add} to {options.input_image}')
  ramdisk_root = os.path.join(options.temp_dir, 'ramdisk_root')
  os.mkdir(ramdisk_root)
  copy_files(options.files_to_add, ramdisk_root)

  unpack_bootimg, mkbootfs, mkbootimg, lz4 = _prepare_env(options.otatools_dir)
  bootimg = BootImage(
      bootimg=options.input_image,
      bootimg_dir=os.path.join(options.temp_dir, 'bootimg'),
      unpack_bootimg_bin=unpack_bootimg,
      mkbootfs_bin=mkbootfs,
      mkbootimg_bin=mkbootimg,
      lz4_bin=lz4)
  bootimg.unpack()
  bootimg.add_ramdisk(ramdisk_root)
  bootimg.pack(options.output_image)


def main(temp_dir: str) -> None:
  args = _parse_args()
  otatools_dir = os.path.join(temp_dir, 'otatools')
  unzip_otatools(args.otatools_zip, otatools_dir, [
      'bin/unpack_bootimg', 'bin/mkbootfs', 'bin/mkbootimg', 'bin/lz4',
      'lib64/*'
  ])
  options = ImageOptions(
      input_image=args.input_img,
      output_image=args.output_img,
      otatools_dir=otatools_dir,
      temp_dir=temp_dir,
      files_to_add=args.add_file)
  add_debug_ramdisk_files(options)


if __name__ == '__main__':
  with tempfile.TemporaryDirectory() as temp_dir:
    main(temp_dir)
