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
    files_to_remove: a list of files to be removed from the input vendor boot
      debug image.
  """
  input_image: str
  output_image: str
  otatools_dir: str
  temp_dir: str
  files_to_add: List[str] = dataclasses.field(default_factory=list)
  files_to_remove: List[str] = dataclasses.field(default_factory=list)


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
    toybox_bin: path of the `toybox` executable.
    bootimg_args: the arguments that were used to build this boot image.
  """
  bootimg: str
  bootimg_dir: str
  unpack_bootimg_bin: str
  mkbootfs_bin: str
  mkbootimg_bin: str
  lz4_bin: str
  toybox_bin: str
  bootimg_args: List[str] = dataclasses.field(default_factory=list)

  def _get_ramdisk_fragments(self) -> List[str]:
    """Get the path to all ramdisk fragments at `self.bootimg_dir`."""
    return [os.path.join(self.bootimg_dir, file)
            for file in os.listdir(self.bootimg_dir)
            if file.startswith('vendor_ramdisk')]

  def _compress_ramdisk(self, root_dir: str, ramdisk_file: str) -> None:
    """Compress all the files under `root_dir` to generate `ramdisk_file`.

    Args:
      root_dir: root directory of the ramdisk content.
      ramdisk_file: path of the output ramdisk file.
    """
    mkbootfs_cmd = [self.mkbootfs_bin, root_dir]
    mkbootfs_result = subprocess.run(
        mkbootfs_cmd, check=True, capture_output=True)
    compress_cmd = [self.lz4_bin, '-l', '-12', '--favor-decSpeed']
    with open(ramdisk_file, 'w') as o:
      subprocess.run(
          compress_cmd, check=True, input=mkbootfs_result.stdout, stdout=o)

  def _decompress_ramdisk(self, ramdisk_file: str, output_dir: str) -> str:
    """Decompress `ramdisk_file` to a new file at `output_dir`.

    Args:
      ramdisk_file: path of the ramdisk file to be decompressed.
      output_dir: path of the output directory.

    Returns:
      Path of the uncompressed ramdisk.
    """
    if not os.path.exists(output_dir):
      raise FileNotFoundError(f'Decompress output {output_dir} does not exist')
    uncompressed_ramdisk = os.path.join(output_dir, 'uncompressed_ramdisk')
    decompress_cmd = [self.lz4_bin, '-d', ramdisk_file, uncompressed_ramdisk]
    subprocess.run(decompress_cmd, check=True)
    return uncompressed_ramdisk

  def _extract_ramdisk(self, ramdisk_file: str, root_dir: str) -> None:
    """Extract the files from a uncompressed ramdisk to `root_dir`.

    Args:
      ramdisk_file: path of the ramdisk file to be extracted.
      root_dir: path of the extracted ramdisk root directory.
    """
    # Use `toybox cpio` instead of `cpio` to avoid invoking cpio from the host
    # environment.
    extract_cmd = [self.toybox_bin, 'cpio', '-i', '-F', ramdisk_file]
    subprocess.run(extract_cmd, cwd=root_dir, check=True)

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
    ramdisk_fragments = self._get_ramdisk_fragments()
    new_ramdisk_name = f'vendor_ramdisk{len(ramdisk_fragments):02d}'
    new_ramdisk_file = os.path.join(self.bootimg_dir, new_ramdisk_name)
    if os.path.exists(new_ramdisk_file):
      raise FileExistsError(f'{new_ramdisk_file} already exists')
    print(f'Adding a new vendor ramdisk fragment {new_ramdisk_file}')
    self._compress_ramdisk(ramdisk_root, new_ramdisk_file)

    # Update the bootimg arguments to include the new ramdisk file.
    self.bootimg_args.extend([
        '--ramdisk_type', _VENDOR_RAMDISK_TYPE_PLATFORM,
        '--ramdisk_name', 'chd',
        '--vendor_ramdisk_fragment', new_ramdisk_file
    ])

  def remove_file(self, file_name: str) -> None:
    """Remove `file_name` from all the existing ramdisk fragments.

    Args:
      file_name: path of the file to be removed, relative to the ramdisk root
        directory.
    """
    ramdisk_fragments = self._get_ramdisk_fragments()
    for ramdisk in ramdisk_fragments:
      print(f'Removing {file_name} from {ramdisk}')
      with tempfile.TemporaryDirectory() as temp_dir:
        uncompressed_ramdisk = self._decompress_ramdisk(ramdisk, temp_dir)
        extracted_ramdisk_dir = os.path.join(temp_dir, 'extracted_ramdisk')
        os.mkdir(extracted_ramdisk_dir)
        self._extract_ramdisk(uncompressed_ramdisk, extracted_ramdisk_dir)

        file_path = os.path.join(extracted_ramdisk_dir, file_name)
        if not os.path.exists(file_path):
          raise FileNotFoundError(f'Cannot Remove {file_name} from {ramdisk}')
        os.remove(file_path)

        self._compress_ramdisk(extracted_ramdisk_dir, ramdisk)

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

  We need `unpack_bootimg`, `mkbootfs`, `mkbootimg`, `lz4` and `toybox` for
  building CHD debug ramdisk. This function returns the path to the above tools
  in order.

  Args:
    otatools_dir: path of the otatools directory.

  Raises:
    FileNotFoundError if any required otatool does not exist.
  """
  tools_path = []
  for tool in ['unpack_bootimg', 'mkbootfs', 'mkbootimg', 'lz4', 'toybox']:
    tool_path = os.path.join(otatools_dir, 'bin', tool)
    if not os.path.exists(tool_path):
      raise FileNotFoundError(f'otatool {tool_path} does not exist')
    tools_path.append(tool_path)
  return tools_path


def build_chd_debug_ramdisk(options: ImageOptions) -> None:
  """Build a new vendor boot debug image.

  1. If `options.files_to_remove` present, remove these files from all the
     existing ramdisk fragments.
  2. If `options.files_to_add` present, create a new ramdisk fragment which
     adds these files, and add this new fragment into the input image.

  Args:
    options: a `ImageOptions` object which specifies the options for building
      a CHD vendor boot debug image.

  Raises:
    FileExistsError if having duplicated ramdisk fragments.
    FileNotFoundError if any required otatool does not exist or if the
      userdebug sepolicy is not present at `input_image`.
  """
  unpack_bootimg, mkbootfs, mkbootimg, lz4, toybox = _prepare_env(
      options.otatools_dir)
  bootimg = BootImage(
      bootimg=options.input_image,
      bootimg_dir=os.path.join(options.temp_dir, 'bootimg'),
      unpack_bootimg_bin=unpack_bootimg,
      mkbootfs_bin=mkbootfs,
      mkbootimg_bin=mkbootimg,
      lz4_bin=lz4,
      toybox_bin=toybox)
  bootimg.unpack()

  for f in options.files_to_remove:
    bootimg.remove_file(f)

  if options.files_to_add:
    print(f'Adding {options.files_to_add} to {options.input_image}')
    new_ramdisk_fragment = os.path.join(options.temp_dir,
                                        'new_ramdisk_fragment')
    os.mkdir(new_ramdisk_fragment)
    copy_files(options.files_to_add, new_ramdisk_fragment)
    bootimg.add_ramdisk(new_ramdisk_fragment)

  bootimg.pack(options.output_image)


def main(temp_dir: str) -> None:
  args = _parse_args()
  otatools_dir = os.path.join(temp_dir, 'otatools')
  unzip_otatools(args.otatools_zip, otatools_dir, [
      'bin/unpack_bootimg', 'bin/mkbootfs', 'bin/mkbootimg', 'bin/lz4',
      'bin/toybox', 'lib64/*'
  ])
  options = ImageOptions(
      input_image=args.input_img,
      output_image=args.output_img,
      otatools_dir=otatools_dir,
      temp_dir=temp_dir,
      files_to_add=args.add_file)
  build_chd_debug_ramdisk(options)


if __name__ == '__main__':
  with tempfile.TemporaryDirectory() as temp_dir:
    main(temp_dir)
