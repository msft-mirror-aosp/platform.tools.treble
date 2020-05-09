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
"""Test config."""

import tempfile
import unittest
from . import config

_TEST_CONFIG_XML = """<config>
  <target name="android_target_1">
    <build_config>
      <goal name="droid"/>
      <goal name="dist"/>
    </build_config>
  </target>
  <target name="android_target_2">
    <build_config>
      <goal name="droid"/>
      <goal name="dist"/>
      <goal name="goal_for_android_target_2"/>
    </build_config>
    <build_config name="build_target_2">
      <goal name="droid"/>
      <goal name="VAR=a"/>
    </build_config>
  </target>
</config>
"""

class ConfigTest(unittest.TestCase):
  """unittest for Config."""

  def setUp(self):
    """Load _TEST_CONFIG_XML into a Config instance."""
    with tempfile.NamedTemporaryFile('w+t') as test_config:
      test_config.write(_TEST_CONFIG_XML)
      test_config.flush()
      self._cfg = config.Config(test_config.name)

  def testAvailableBuildTargets(self):
    self.assertEqual(
        self._cfg.get_available_build_targets(),
        # Sorted, not lexical.
        [
            'android_target_1',
            'android_target_2',
            'build_target_2',
        ])

  def testBuildTargetToAndroidTarget(self):
    # Test that build_target android_target_1 -> android_target_1.
    self.assertEqual(
        self._cfg.get_build_config_android_target('android_target_1'),
        'android_target_1')

    # Test that build_target android_target_2 -> android_target_2.
    self.assertEqual(
        self._cfg.get_build_config_android_target('android_target_2'),
        'android_target_2')

    # Test that build_target build_target_2 -> android_target_2.
    self.assertEqual(
        self._cfg.get_build_config_android_target('build_target_2'),
        'android_target_2')

  def testBuildTargetToBuildGoals(self):
    # Test that build_target android_target_1 has goals droid and dist.
    self.assertEqual(
        self._cfg.get_build_config_build_goals('android_target_1'),
        ['droid', 'dist'])

    # Test that build_target android_target_2 has goals droid, dist, and
    # goal_for_android_target_2.
    self.assertEqual(
        self._cfg.get_build_config_build_goals('android_target_2'),
        ['droid', 'dist', 'goal_for_android_target_2'])

    # Test that build_target build_target_2 has goals droid and VAR=a.
    self.assertEqual(
        self._cfg.get_build_config_build_goals('build_target_2'),
        ['droid', 'VAR=a'])


if __name__ == '__main__':
  unittest.main()
