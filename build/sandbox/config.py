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

# The config file must be in XML with a structure as descibed below.
#
# The top level config element shall contain one or more "target" child elements.
# Each of these conrresponds to a different Android "lunch" build configuration
# target.
#
# Each "target" may contain the following:
#
# Properties:
#
#   name: The name of the target.
#
# Child elements:
#
#   fast_merge_config: The configuration options for fast merge.
#
#     Properties:
#
#       framework_images: Comma-separated list of image names that
#         should come from the framework build.
#
#       misc_info_keys: A path to the newline-separated config file containing
#       keys to obtain from the framework instance of misc_info.txt, used for
#       creating vbmeta.img.
#
#   overlay: An overlay to be mounted while building the target.
#
#     Properties:
#
#       name: The name of the overlay.
#
#   view: A map (optionally) specifying a filesystem view mapping for each
#     target.
#
#     Properties:
#
#       name: The name of the view.
#
#   allow_readwrite: A folder to mount read/write
#   inside the Android build nsjail. Each allowed read-write entry should be
#   accompanied by a bug that indicates why it was required and tracks the
#   progress to a fix.
#
#     Properties:
#
#       path: The path to be allowed read-write mounting.
#
#   build_config: A list of goals to be used while building the target.
#
#     Properties:
#
#       name: The name of the build config. Defaults to the target name
#         if not set.
#
#     Child elements:
#
#       goal: A build goal.
#
#         Properties:
#
#           name: The name of the build goal. Below are described some
#             build goals that are common to most targets.

def _get_build_config_map(config):
  """Retrieves a map of all build config.

  Args:
    config: An XML Element that is the root of the config XML tree.

  Returns:
    A dict of build configs keyed by name. Each build config is itself a dict
    with two items: an 'android_target' item with a string name, and a
    'build_goals' item with list of string build goals.
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


def _get_rw_whitelist_map(config):
  """Retrieves the map of allowed read-write paths for each target.

  Args:
    config: An XML Element that is the root of the config XML tree.

  Returns:
    A dict of string lists of keyed by target name. Each value in the dict is a
    list of allowed read-write paths corresponding to the target.
  """
  rw_whitelist_map = {}
  for target in config.findall('target'):
    name = target.get('name')
    rw_whitelist = [a.get('path') for a in target.findall('allow_readwrite')]
    rw_whitelist_map[name] = rw_whitelist

  return rw_whitelist_map


def _get_overlay_map(config):
  """Retrieves the map of overlays for each target.

  Args:
    config: An XML Element that is the root of the config XML tree.

  Returns:
    A dict of keyed by target name. Each value in the dict is a list of overlay
    names corresponding to the target.
  """
  overlay_map = {}
  for target in config.findall('target'):
    name = target.get('name')
    overlay_list = [o.get('name') for o in target.findall('overlay')]
    overlay_map[name] = overlay_list
  # A valid configuration file is required to have at least one overlay target.
  if not overlay_map:
    raise ValueError('Error: the overlay configuration file is missing at '
                     'least one overlay target')

  return overlay_map


def _get_fs_view_map(config):
  """Retrieves the map of filesystem views for each target.

  Args:
    config: An XML Element that is the root of the config XML tree.

  Returns:
    A dict of filesystem views keyed by target name. A filesystem view is a
    list of (source, destination) string path tuples.
  """
  fs_view_map = {}
  # A valid config file is not required to include FS Views, only overlay
  # targets.
  views = {}
  for view in config.findall('view'):
    name = view.get('name')
    paths = []
    for path in view.findall('path'):
      paths.append((path.get('source'), path.get('destination')))
    views[name] = paths

  for target in config.findall('target'):
    target_name = target.get('name')
    view_paths = []
    for view in target.findall('view'):
      view_paths.extend(views[view.get('name')])

    if view_paths:
      fs_view_map[target_name] = view_paths

  return fs_view_map


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
    self._fs_view_map = _get_fs_view_map(config)
    self._overlay_map = _get_overlay_map(config)
    self._rw_whitelist_map = _get_rw_whitelist_map(config)

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

  def get_rw_whitelist_map(self):
    """Return read-write whitelist map.

    Returns:
      A dict of string lists of keyed by target name. Each value in the dict is
      a list of allowed read-write paths corresponding to the target.
    """
    return self._rw_whitelist_map

  def get_overlay_map(self):
    """Return the overlay map.

    Returns:
      A dict of keyed by target name. Each value in the dict is a list of
      overlay names corresponding to the target.
    """
    return self._overlay_map

  def get_fs_view_map(self):
    """Return the filesystem view map.
    Returns:
      A dict of filesystem views keyed by target name. A filesystem view is a
      list of (source, destination) string path tuples.
    """
    return self._fs_view_map

def factory(config_filename):
  """Create an instance of a Config class.

  Args:
    config_filename: The name of the file from which to load the config. This
      can be None, which results in this function returning None.

  Returns:
    If config_filename is None, returns None. Otherwise, a new instance of a
    Config class containing the configuration parsed from config_filename.
  """
  if config_filename is None:
    return None

  return Config(config_filename)
