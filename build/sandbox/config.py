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

"""Parses config file and provides various ways of using it."""

import xml.etree.ElementTree as ET

def _get_build_config_map(config):
  """Retrieves a map of all build config.

  Args:
    config: An XML Element that is the root of the config XML tree.

  Returns:
    A dict of build configs keyed by name. Each build config
    is itself a dict with two items: an 'android_target' item
    with a string name, and a 'build_goals' item with list of string
    build goals.
  """
  build_config_map = {}
  for target in config.findall('target'):
    target_name = target.get('name')
    for build_config in target.findall('build_config'):
      # The build config name defaults to the target name
      build_config_name = build_config.get('name') or target_name
      goal_list = [g.get('name') for g in build_config.findall('goal')]
      # A valid build_config is required to have at least one overlay target.
      if not goal_list:
        raise ValueError(
            'Error: build_config %s must have at least one goal' %
            build_config_name)
      build_config_map[build_config_name] = {
          'android_target': target_name,
          'build_goals': goal_list,
      }
  return build_config_map


class Config:
  """Presents an API to the static XML configuration."""

  def __init__(self, config_filename):
    """Initializes a Config instance from the specificed filename

    This method parses the XML content of the file named by config_filename
    into internal data structures. You can then use various methods to query
    the static config.

    Args:
      config_filename: The name of the file from which to load the config.
    """

    tree = ET.parse(config_filename)
    config = tree.getroot()
    self._build_config_map = _get_build_config_map(config)

  def get_available_build_targets(self):
    """Return a list of available build targets."""
    return sorted(self._build_config_map.keys())

  def get_build_config_android_target(self, build_target):
    """Given a build_target, return an android_target.

    Generally a build_target maps directory to the android_target of the same
    name, but they can differ. In a config.xml file, the name attribute of a
    target element is the android_target (which is used for lunch). The name
    attribute (if any) of a build_config element is the build_target. If a
    build_config element does not have a name attribute, then the build_target
    is the android_target.

    Args:
      build_target: A string build_target to be queried.

    Returns:
      A string android_target that can be used for lunch.
    """
    return self._build_config_map[build_target]['android_target']

  def get_build_config_build_goals(self, build_target):
    """Given a build_target, return build goals.

    Args:
      build_target: A string build_target to be queried.
    Returns:
      A list of strings, where each string is a goal to be passed to make.
    """
    return self._build_config_map[build_target]['build_goals']
