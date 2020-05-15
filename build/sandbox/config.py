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
# The top level config element shall contain one or more "target" child
# elements. Each of these conrresponds to a different Android "lunch" build
# configuration target.
#
# Each "target" may contain the following:
#
# Properties:
#
#   name: The name of the target.
#
#   tags: A comma-separated list of strings to be associated with the target
#     and any of its nested build_targets. You can use a tag to associate
#     information with a target in your configuration file, and retrieve that
#     information using the get_tags API or the has_tag API.
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
#           name: The name of the build goal. The build tools pass the name
#             attribute as a parameter to make. This can have a value like
#             "droid" or "VAR=value".
#
#           contexts: A comma-separated list of the contexts in which this
#             goal applies. If this attribute is missing or blank, the goal
#             applies to all contexts. Otherwise, it applies only in the
#             requested contexts (see get_build_goals).


def _get_build_config_goals(build_config):
  """Retrieves goals from build_config.

  Args:
    build_config: A build_config xml element.

  Returns:
    A list of tuples where the first element of the tuple is the build goal
    name, and the second is a list of the contexts to which this goal applies.
  """
  goals = []

  for goal in build_config.findall('goal'):
    goal_name = goal.get('name')
    goal_contexts = goal.get('contexts')

    if goal_contexts:
      goal_contexts = set(goal_contexts.split(','))
      if goal_contexts:
        goals.append((goal_name, goal_contexts))
    else:
      goals.append((goal_name, set()))

  return goals


def _get_build_config_map(config):
  """Retrieves a map of all build config.

  Args:
    config: An XML Element that is the root of the config XML tree.

  Returns:
    A dict of build configs keyed by build_target. Each build config is itself
    a dict with three items: an 'android_target' item with a string name of the
    android_target to use for this build_target, a 'tags' item with a set of
    the string tags, and a 'build_goals' item with list of build goals tuples.
  """
  build_config_map = {}
  for target in config.findall('target'):
    target_name = target.get('name')
    tags = target.get('tags')
    target_tags = set(tags.split(',')) if tags else set()
    for build_config in target.findall('build_config'):
      # The build config name defaults to the target name
      build_config_name = build_config.get('name') or target_name
      goal_list = _get_build_config_goals(build_config)
      # A valid build_config is required to have at least one overlay target.
      if not goal_list:
        raise ValueError(
            'Error: build_config %s must have at least one goal' %
            build_config_name)
      build_config_map[build_config_name] = {
          'android_target': target_name,
          'tags': target_tags,
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

  def get_tags(self, build_target):
    """Given a build_target, return the (possibly empty) set of tags."""
    return self._build_config_map[build_target]['tags']

  def has_tag(self, build_target, tag):
    """Return true if build_target has tag.

    Args:
      build_target: A string build_target to be queried.
      tag: A string tag that this target may have.

    Returns:
      If the build_target has the tag, True. Otherwise, False.
    """
    return tag in self._build_config_map[build_target]['tags']

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

  def get_build_goals(self, build_target, contexts=None):
    """Given a build_target and a context, return a list of build goals.

    For a given build_target, we may build in a variety of contexts. For
    example we might build in continuous integration, or we might build
    locally, or other contexts defined by the configuration file and scripts
    that use it. The contexts parameter is a set of strings that specify the
    contexts for which this function should retrieve goals.

    In the configuration file, each goal has a contexts attribute, which
    specifies the contexts to which the goal applies. We treat a goal with no
    contexts attribute as applying to all contexts.

    Example:

      <build_config>
        <goal name="droid"/>
        <goal name="dist" contexts="ota"/>
      </build_config>

      Here we have the goal "droid", which matches all contexts, and the goal
      "dist", which matches the "ota" context. Invoking this method with the
      set(['ota']) would return ['droid', 'dist'].

    Args:
      build_target: A string build_target to be queried.
      context: A set of contexts for which to retrieve goals.

    Returns:
      A list of strings, where each string is a goal to be passed to make.
    """
    build_goals = []

    if contexts is None:
      contexts = set()

    for build_goal in self._build_config_map[build_target]['build_goals']:

      # build_goal is a tuple of (name, contexts), where name is the string
      # name of the of goal to be passed to make, and contexts is a set use to
      # match the requested contexts.

      if build_goal[1]:
        # If we have a non-empty contexts set attached to the goal, include the
        # goal only if the caller requested the context.
        if contexts & build_goal[1]:
          build_goals.append(build_goal[0])
      else:
        # If there is an empty contexts set attached to the goal, always
        # included the goal.
        build_goals.append(build_goal[0])

    return build_goals

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
