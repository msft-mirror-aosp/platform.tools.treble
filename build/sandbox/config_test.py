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
  <target name="android_target_2" tags="cool,hot">
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
  <target name="android_target_3" tags="">
    <build_config>
      <goal name="droid"/>
    </build_config>
  </target>
</config>
"""

_TEST_CONTEXTS_CONFIG_XML = """<config>
  <target name="test_target">
    <build_config>

      <!-- no contexts attribute: always selected -->
      <goal name="droid"/>

      <!-- empty contexts attribute: always selected -->
      <goal name="always" contexts=""/>

      <!-- selected if ci context requested -->
      <goal name="dist" contexts="ci"/>

      <!-- selected if x context requested -->
      <goal name="VAR=value" contexts="x"/>

      <!-- selected if ci or x context requested -->
      <goal name="extra_goal" contexts="ci,x"/>

    </build_config>
  </target>
</config>
"""

class ConfigTest(unittest.TestCase):
  """unittest for Config."""

  def testConfigFilenameNone(self):
    cfg = config.factory(None)
    self.assertIsNone(cfg)

  def testAvailableBuildTargets(self):
    with tempfile.NamedTemporaryFile('w+t') as test_config:
      test_config.write(_TEST_CONFIG_XML)
      test_config.flush()
      cfg = config.factory(test_config.name)
      self.assertEqual(
          cfg.get_available_build_targets(),
          # Sorted; not in document order.
          [
              'android_target_1',
              'android_target_2',
              'android_target_3',
              'build_target_2',
          ])

  def testBuildTargetTags(self):
    with tempfile.NamedTemporaryFile('w+t') as test_config:
      test_config.write(_TEST_CONFIG_XML)
      test_config.flush()
      cfg = config.factory(test_config.name)

      self.assertEqual(cfg.get_tags('android_target_1'), set())
      self.assertEqual(cfg.get_tags('android_target_2'), set(['cool', 'hot']))
      self.assertEqual(cfg.get_tags('build_target_2'), set(['cool', 'hot']))
      self.assertEqual(cfg.get_tags('android_target_3'), set())

      self.assertFalse(cfg.has_tag('android_target_1', 'cool'))
      self.assertFalse(cfg.has_tag('android_target_1', 'hot'))
      self.assertFalse(cfg.has_tag('android_target_1', 'meh'))

      self.assertTrue(cfg.has_tag('android_target_2', 'cool'))
      self.assertTrue(cfg.has_tag('android_target_2', 'hot'))
      self.assertFalse(cfg.has_tag('android_target_2', 'meh'))

      self.assertTrue(cfg.has_tag('build_target_2', 'cool'))
      self.assertTrue(cfg.has_tag('build_target_2', 'hot'))
      self.assertFalse(cfg.has_tag('build_target_2', 'meh'))

      self.assertFalse(cfg.has_tag('android_target_3', 'cool'))
      self.assertFalse(cfg.has_tag('android_target_3', 'hot'))
      self.assertFalse(cfg.has_tag('android_target_3', 'meh'))

  def testBuildTargetToAndroidTarget(self):
    with tempfile.NamedTemporaryFile('w+t') as test_config:
      test_config.write(_TEST_CONFIG_XML)
      test_config.flush()
      cfg = config.factory(test_config.name)

      # Test that build_target android_target_1 -> android_target_1.
      self.assertEqual(
          cfg.get_build_config_android_target('android_target_1'),
          'android_target_1')

      # Test that build_target android_target_2 -> android_target_2.
      self.assertEqual(
          cfg.get_build_config_android_target('android_target_2'),
          'android_target_2')

      # Test that build_target build_target_2 -> android_target_2.
      self.assertEqual(
          cfg.get_build_config_android_target('build_target_2'),
          'android_target_2')

  def testBuildTargetToBuildGoals(self):
    with tempfile.NamedTemporaryFile('w+t') as test_config:
      test_config.write(_TEST_CONFIG_XML)
      test_config.flush()
      cfg = config.factory(test_config.name)

      # Test that build_target android_target_1 has goals droid and dist.
      self.assertEqual(
          cfg.get_build_goals('android_target_1'),
          ['droid', 'dist'])

      # Test that build_target android_target_2 has goals droid, dist, and
      # goal_for_android_target_2.
      self.assertEqual(
          cfg.get_build_goals('android_target_2'),
          ['droid', 'dist', 'goal_for_android_target_2'])

      # Test that build_target build_target_2 has goals droid and VAR=a.
      self.assertEqual(
          cfg.get_build_goals('build_target_2'),
          ['droid', 'VAR=a'])

  def testBuildTargetToBuildGoalsWithContexts(self):
    with tempfile.NamedTemporaryFile('w+t') as test_config:
      test_config.write(_TEST_CONTEXTS_CONFIG_XML)
      test_config.flush()
      cfg = config.factory(test_config.name)

      # Test that when contexts is the default (empty), we select only the
      # "always" goals.

      build_goals = cfg.get_build_goals('test_target')
      self.assertEqual(build_goals, ['droid', 'always'])

      # Test that when contexts is explicitly empty, we select only the
      # "always" goals.

      build_goals = cfg.get_build_goals('test_target', set())
      self.assertEqual(build_goals, ['droid', 'always'])

      # Similarly, test that when contexts is doesn't match any goal_contexts,
      # we select only the "always" goals.

      build_goals = cfg.get_build_goals('test_target', set('no_matchy'))
      self.assertEqual(build_goals, ['droid', 'always'])

      # Test that when contexts is set(['x']), we select the "always" goals and
      # the x goals.

      build_goals = cfg.get_build_goals('test_target', set(['x']))

      self.assertEqual(
          build_goals,
          ['droid', 'always', 'VAR=value', 'extra_goal'])

      # Test that when requested_contexts is set(['ci', 'x']), we select the
      # "always" goals, the ci goals, and the x goals.

      build_goals = cfg.get_build_goals('test_target', set(['ci', 'x']))

      self.assertEqual(
          build_goals,
          ['droid', 'always', 'dist', 'VAR=value', 'extra_goal'])


if __name__ == '__main__':
  unittest.main()
