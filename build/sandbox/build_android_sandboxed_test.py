# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Test build_android_sandboxed."""

import os
import unittest
from . import build_android_sandboxed


class BuildAndroidSandboxedTest(unittest.TestCase):

  def testBasic(self):
    build_android_sandboxed.nsjail.__file__ = '/'
    os.chdir('/')
    commands = build_android_sandboxed.build(
        'target_name',
        'userdebug',
        nsjail_bin='/bin/true',
        chroot='/chroot',
        dist_dir='/dist_dir',
        build_id='0',
        max_cpus=1,
        build_goals=['droid', 'dist'])

    self.assertEqual(
        commands,
        [
            '/bin/true',
            '--env', 'USER=nobody',
            '--config', '/nsjail.cfg',
            '--env', 'BUILD_NUMBER=0',
            '--max_cpus=1',
            '--env', 'DIST_DIR=/dist',
            '--bindmount', '/:/src',
            '--bindmount', '/dist_dir:/dist',
            '--',
            '/src/tools/treble/build/sandbox/build_android_target.sh',
            'target_name-userdebug',
            '/src',
            'make', '-j', 'droid', 'dist',
        ]
    )

  def testUser(self):
    build_android_sandboxed.nsjail.__file__ = '/'
    os.chdir('/')
    commands = build_android_sandboxed.build(
        'target_name',
        'user',
        nsjail_bin='/bin/true',
        chroot='/chroot',
        dist_dir='/dist_dir',
        build_id='0',
        max_cpus=1,
        build_goals=['droid', 'dist'])

    self.assertEqual(
        commands,
        [
            '/bin/true',
            '--env', 'USER=nobody',
            '--config', '/nsjail.cfg',
            '--env', 'BUILD_NUMBER=0',
            '--max_cpus=1',
            '--env', 'DIST_DIR=/dist',
            '--bindmount', '/:/src',
            '--bindmount', '/dist_dir:/dist',
            '--',
            '/src/tools/treble/build/sandbox/build_android_target.sh',
            'target_name-user',
            '/src',
            'make', '-j', 'droid', 'dist',
        ]
    )

  def testExtraBuildGoals(self):
    build_android_sandboxed.nsjail.__file__ = '/'
    os.chdir('/')
    commands = build_android_sandboxed.build(
        'target_name',
        'userdebug',
        nsjail_bin='/bin/true',
        chroot='/chroot',
        dist_dir='/dist_dir',
        build_id='0',
        max_cpus=1,
        build_goals=['droid', 'dist', 'extra_build_target'])

    self.assertEqual(
        commands,
        [
            '/bin/true',
            '--env', 'USER=nobody',
            '--config', '/nsjail.cfg',
            '--env', 'BUILD_NUMBER=0',
            '--max_cpus=1',
            '--env', 'DIST_DIR=/dist',
            '--bindmount', '/:/src',
            '--bindmount', '/dist_dir:/dist',
            '--',
            '/src/tools/treble/build/sandbox/build_android_target.sh',
            'target_name-userdebug',
            '/src',
            'make', '-j', 'droid', 'dist',
            'extra_build_target'
        ]
    )

if __name__ == '__main__':
  unittest.main()
