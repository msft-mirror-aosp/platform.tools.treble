# Copyright (C) 2020 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Splits a manifest to the minimum set of projects needed to build the targets.

Usage: manifest_split [options] targets

targets: Space-separated list of targets that should be buildable
         using the split manifest.

options:
  --manifest <path>
      Path to the repo manifest to split. [Required]
  --split-manifest <path>
      Path to write the resulting split manifest. [Required]
  --config <path>
      Optional path(s) to a config XML file containing projects to add or
      remove. See default_config.xml for an example. This flag can be passed
      more than once to use multiple config files.
        Sample file my_config.xml:
          <config>
            <add_project name="vendor/my/needed/project" />
            <remove_project name="vendor/my/unused/project" />
          </config>
  --repo-list <path>
      Optional path to the output of the 'repo list' command. Used if the
      output of 'repo list' needs pre-processing before being used by
      this tool.
  --ninja-build <path>
      Optional path to the combined-<target>.ninja file found in an out dir.
      If not provided, the default file is used based on the lunch environment.
  --ninja-binary <path>
      Optional path to the ninja binary. Uses the standard binary by default.
  --module-info <path>
      Optional path to the module-info.json file found in an out dir.
      If not provided, the default file is used based on the lunch environment.
  --kati-stamp <path>
      Optional path to the .kati_stamp file found in an out dir.
      If not provided, the default file is used based on the lunch environment.
  --overlay <path>
      Optional path(s) to treat as overlays when parsing the kati stamp file
      and scanning for makefiles. See the tools/treble/build/sandbox directory
      for more info about overlays. This flag can be passed more than once.
  --debug-file <path>
      If provided, debug info will be written to a JSON file at this path.
  -h  (--help)
      Display this usage message and exit.
"""

from __future__ import print_function

import getopt
import hashlib
import json
import logging
import os
import pkg_resources
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s - %(filename)s - %(levelname)-8s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(os.path.basename(__file__))

# Projects determined to be needed despite the dependency not being visible
# to ninja.
DEFAULT_CONFIG_PATH = pkg_resources.resource_filename(__name__,
                                                      "default_config.xml")

# Pattern that matches a java dependency.
_JAVA_LIB_PATTERN = re.compile(
    # pylint: disable=line-too-long
    '^out/target/common/obj/JAVA_LIBRARIES/(.+)_intermediates/classes-header.jar$'
)

def read_config(config_file):
  """Reads a config XML file to find extra projects to add or remove.

  Args:
    config_file: The filename of the config XML.

  Returns:
    A tuple of (set of remove_projects, set of add_projects) from the config.
  """
  root = ET.parse(config_file).getroot()
  remove_projects = set(
      [child.attrib["name"] for child in root.findall("remove_project")])
  add_projects = set(
      [child.attrib["name"] for child in root.findall("add_project")])
  return remove_projects, add_projects


def get_repo_projects(repo_list_file):
  """Returns a dict of { project path : project name } using 'repo list'.

  Args:
    repo_list_file: An optional filename to read instead of calling the repo
      list command.
  """
  repo_list = []

  if repo_list_file:
    with open(repo_list_file) as repo_list_lines:
      repo_list = [line.strip() for line in repo_list_lines if line.strip()]
  else:
    repo_list = subprocess.check_output([
        "repo",
        "list",
    ]).decode().strip("\n").split("\n")
  return dict([entry.split(" : ") for entry in repo_list])


class ModuleInfo:
  """Contains various mappings to/from module/project"""

  def __init__(self, module_info_file, repo_projects):
    """Initialize a module info instance.

    Builds various maps related to platform build system modules and how they
    relate to each other and projects.

    Args:
      module_info_file: The path to a module-info.json file from a build.
      repo_projects: The output of the get_repo_projects function.

    Raises:
      ValueError: A module from module-info.json belongs to a path not
        known by the repo projects output.
    """
    # Maps a project to the set of modules it contains.
    self.project_modules = {}
    # Maps a module to the project that contains it.
    self.module_project = {}
    # Maps a module to its class.
    self.module_class = {}
    # Maps a module to modules it depends on.
    self.module_deps = {}

    with open(module_info_file) as module_info_file:
      module_info = json.load(module_info_file)

    def module_has_valid_path(module):
      return ("path" in module_info[module] and module_info[module]["path"] and
              not module_info[module]["path"][0].startswith("out/"))

    module_paths = {
        module: module_info[module]["path"][0]
        for module in module_info
        if module_has_valid_path(module)
    }
    module_project_paths = {
        module: scan_repo_projects(repo_projects, module_paths[module])
        for module in module_paths
    }

    for module, project_path in module_project_paths.items():
      if not project_path:
        raise ValueError("Unknown module path for module %s: %s" %
                         (module, module_info[module]))
      repo_project = repo_projects[project_path]
      self.project_modules.setdefault(repo_project, set()).add(module)
      self.module_project[module] = repo_project

    def dep_from_raw_dep(raw_dep):
      match = re.search(_JAVA_LIB_PATTERN, raw_dep)
      return match.group(1) if match else raw_dep

    def deps_from_raw_deps(raw_deps):
      return [dep_from_raw_dep(raw_dep) for raw_dep in raw_deps]

    self.module_class = {
        module: module_info[module]["class"][0]
        for module in module_info
    }
    self.module_deps = {
        module: deps_from_raw_deps(module_info[module]["dependencies"])
        for module in module_info
    }


def get_ninja_inputs(ninja_binary, ninja_build_file, modules):
  """Returns the set of input file path strings for the given modules.

  Uses the `ninja -t inputs` tool.

  Args:
    ninja_binary: The path to a ninja binary.
    ninja_build_file: The path to a .ninja file from a build.
    modules: The list of modules to scan for inputs.
  """
  inputs = set()
  NINJA_SHARD_LIMIT = 20000
  for i in range(0, len(modules), NINJA_SHARD_LIMIT):
    modules_shard = modules[i:i + NINJA_SHARD_LIMIT]
    inputs = inputs.union(set(
        subprocess.check_output([
            ninja_binary,
            "-f",
            ninja_build_file,
            "-t",
            "inputs",
            "-d",
        ] + list(modules_shard)).decode().strip("\n").split("\n")))

  def input_allowed(path):
    path = path.strip()
    if path.endswith("TEST_MAPPING") and "test_mapping" not in modules:
      # Exclude projects that are only needed for TEST_MAPPING files, unless the
      # user is asking to build 'test_mapping'.
      return False
    if path.endswith("MODULE_LICENSE_GPL"):
      # Exclude projects that are included only due to having a
      # MODULE_LICENSE_GPL file, if no other inputs from that project are used.
      return False
    return path

  return {path.strip() for path in inputs if input_allowed(path)}


def get_kati_makefiles(kati_stamp_file, overlays):
  """Returns the set of makefile paths from the kati stamp file.

  Uses the ckati_stamp_dump prebuilt binary.
  Also includes symlink sources in the resulting set for any
  makefiles that are symlinks.

  Args:
    kati_stamp_file: The path to a .kati_stamp file from a build.
    overlays: A list of paths to treat as overlays when parsing the kati stamp
      file.
  """
  # Get a set of all makefiles that were parsed by Kati during the build.
  makefiles = set(
      subprocess.check_output([
          "prebuilts/build-tools/linux-x86/bin/ckati_stamp_dump",
          "--files",
          kati_stamp_file,
      ]).decode().strip("\n").split("\n"))

  def is_product_makefile(makefile):
    """Returns True if the makefile path meets certain criteria."""
    banned_prefixes = [
        "out/",
        # Ignore product makefiles for sample AOSP boards.
        "device/amlogic",
        "device/generic",
        "device/google",
        "device/linaro",
        "device/sample",
    ]
    banned_suffixes = [
        # All Android.mk files in the source are always parsed by Kati,
        # so including them here would bring in lots of unnecessary projects.
        "Android.mk",
        # The ckati stamp file always includes a line for the ckati bin at
        # the beginnning.
        "bin/ckati",
    ]
    return (all([not makefile.startswith(p) for p in banned_prefixes]) and
            all([not makefile.endswith(s) for s in banned_suffixes]))

  # Limit the makefiles to only product makefiles.
  product_makefiles = {
      os.path.normpath(path) for path in makefiles if is_product_makefile(path)
  }

  def strip_overlay(makefile):
    """Remove any overlays from a makefile path."""
    for overlay in overlays:
      if makefile.startswith(overlay):
        return makefile[len(overlay):]
    return makefile

  makefiles_and_symlinks = set()
  for makefile in product_makefiles:
    # Search for the makefile, possibly scanning overlays as well.
    for overlay in [""] + overlays:
      makefile_with_overlay = os.path.join(overlay, makefile)
      if os.path.exists(makefile_with_overlay):
        makefile = makefile_with_overlay
        break

    if not os.path.exists(makefile):
      logger.warning("Unknown kati makefile: %s" % makefile)
      continue

    # Ensure the project that contains the makefile is included, as well as
    # the project that any makefile symlinks point to.
    makefiles_and_symlinks.add(strip_overlay(makefile))
    if os.path.islink(makefile):
      makefiles_and_symlinks.add(
          strip_overlay(os.path.relpath(os.path.realpath(makefile))))

  return makefiles_and_symlinks


def scan_repo_projects(repo_projects, input_path):
  """Returns the project path of the given input path if it exists.

  Args:
    repo_projects: The output of the get_repo_projects function.
    input_path: The path of an input file used in the build, as given by the
      ninja inputs tool.

  Returns:
    The path string, or None if not found.
  """
  parts = input_path.split("/")

  for index in reversed(range(0, len(parts))):
    project_path = os.path.join(*parts[:index + 1])
    if project_path in repo_projects:
      return project_path

  return None


def get_input_projects(repo_projects, inputs):
  """Returns the collection of project names that contain the given input paths.

  Args:
    repo_projects: The output of the get_repo_projects function.
    inputs: The paths of input files used in the build, as given by the ninja
      inputs tool.
  """
  input_project_paths = {}
  for input_path in inputs:
    if not input_path.startswith("out/") and not input_path.startswith("/"):
      input_project_paths.setdefault(
          scan_repo_projects(repo_projects, input_path), []).append(input_path)

  return {
      repo_projects[project_path]: inputs
      for project_path, inputs in input_project_paths.items()
      if project_path is not None
  }


def update_manifest(manifest, input_projects, remove_projects):
  """Modifies and returns a manifest ElementTree by modifying its projects.

  Args:
    manifest: The manifest object to modify.
    input_projects: A set of projects that should stay in the manifest.
    remove_projects: A set of projects that should be removed from the manifest.
      Projects in this set override input_projects.

  Returns:
    The modified manifest object.
  """
  projects_to_keep = input_projects.difference(remove_projects)
  root = manifest.getroot()
  for child in root.findall("project"):
    if child.attrib["name"] not in projects_to_keep:
      root.remove(child)
  return manifest


def create_manifest_sha1_element(manifest, name):
  """Creates and returns an ElementTree 'hash' Element using a sha1 hash.

  Args:
    manifest: The manifest ElementTree to hash.
    name: The name string to give this element.

  Returns:
    The ElementTree 'hash' Element.
  """
  sha1_element = ET.Element("hash")
  sha1_element.set("type", "sha1")
  sha1_element.set("name", name)
  sha1_element.set("value",
                   hashlib.sha1(ET.tostring(manifest.getroot())).hexdigest())
  return sha1_element


class DebugInfo():
  """Simple class to store structured debug info for a project."""

  def __init__(self):
    self.direct_input = False
    self.adjacent_input = False
    self.deps_input = False
    self.kati_makefiles = []
    self.manual_add_configs = []
    self.manual_remove_configs = []


def create_split_manifest(targets, manifest_file, split_manifest_file,
                          config_files, repo_list_file, ninja_build_file,
                          ninja_binary, module_info_file, kati_stamp_file,
                          overlays, debug_file):
  """Creates and writes a split manifest by inspecting build inputs.

  Args:
    targets: List of targets that should be buildable using the split manifest.
    manifest_file: Path to the repo manifest to split.
    split_manifest_file: Path to write the resulting split manifest.
    config_files: Paths to a config XML file containing projects to add or
      remove. See default_config.xml for an example. This flag can be passed
      more than once to use multiple config files.
    repo_list_file: Path to the output of the 'repo list' command.
    ninja_build_file: Path to the combined-<target>.ninja file found in an out
      dir.
    ninja_binary: Path to the ninja binary.
    module_info_file: Path to the module-info.json file found in an out dir.
    kati_stamp_file: The path to a .kati_stamp file from a build.
    overlays: A list of paths to treat as overlays when parsing the kati stamp
      file.
    debug_file: If not None, the path to write JSON debug info.
  """
  debug_info = {}

  remove_projects = {}
  add_projects = {}
  for config_file in config_files:
    config_remove_projects, config_add_projects = read_config(config_file)
    for project in config_remove_projects:
      remove_projects.setdefault(project, []).append(config_file)
    for project in config_add_projects:
      add_projects.setdefault(project, []).append(config_file)

  repo_projects = get_repo_projects(repo_list_file)
  module_info = ModuleInfo(module_info_file, repo_projects)

  inputs = get_ninja_inputs(ninja_binary, ninja_build_file, targets)
  input_projects = set(get_input_projects(repo_projects, inputs).keys())
  for project in input_projects:
    debug_info.setdefault(project, DebugInfo()).direct_input = True
  logger.info(
      "%s projects needed for Ninja-graph direct dependencies of targets \"%s\"",
      len(input_projects), " ".join(targets))

  kati_makefiles = get_kati_makefiles(kati_stamp_file, overlays)
  kati_makefiles_projects = get_input_projects(repo_projects, kati_makefiles)
  for project, makefiles in kati_makefiles_projects.items():
    debug_info.setdefault(project, DebugInfo()).kati_makefiles = makefiles
  input_projects = input_projects.union(kati_makefiles_projects.keys())
  logger.info("%s projects after including Kati makefiles projects.",
              len(input_projects))

  for project, configs in add_projects.items():
    debug_info.setdefault(project, DebugInfo()).manual_add_configs = configs
  for project, configs in remove_projects.items():
    debug_info.setdefault(project, DebugInfo()).manual_remove_configs = configs
  input_projects = input_projects.union(add_projects.keys())
  logger.info("%s projects after including manual additions.",
              len(input_projects))

  # Remove projects from our set of input projects before adding adjacent
  # modules, so that no project is added only because of an adjacent
  # dependency in a to-be-removed project.
  input_projects = input_projects.difference(remove_projects.keys())

  # While we still have projects whose modules we haven't checked yet,
  checked_projects = set()
  projects_to_check = input_projects.difference(checked_projects)

  logger.info("Checking module-info dependencies for direct and adjacent modules...")
  iteration = 0

  while projects_to_check:
    iteration += 1
    # check all modules in each project,
    modules = []
    deps_additions = set()

    def process_deps(module):
      for d in module_info.module_deps[module]:
        if d in module_info.module_class:
          if module_info.module_class[d] == "HEADER_LIBRARIES":
            hla = module_info.module_project[d]
            if hla not in input_projects:
              deps_additions.add(hla)

    for project in projects_to_check:
      checked_projects.add(project)
      if project not in module_info.project_modules:
        continue
      for module in module_info.project_modules[project]:
        modules.append(module)
        process_deps(module)

    for project in deps_additions:
      debug_info.setdefault(project, DebugInfo()).deps_input = True
    input_projects = input_projects.union(deps_additions)
    logger.info(
        "pass %d - %d projects after including HEADER_LIBRARIES dependencies",
        iteration, len(input_projects))

    # adding those modules' input projects to our list of projects.
    inputs = get_ninja_inputs(ninja_binary, ninja_build_file, modules)
    adjacent_module_additions = set(
        get_input_projects(repo_projects, inputs).keys())
    for project in adjacent_module_additions:
      debug_info.setdefault(project, DebugInfo()).adjacent_input = True
    input_projects = input_projects.union(adjacent_module_additions)
    logger.info(
        "pass %d - %d projects after including adjacent-module Ninja-graph dependencies",
        iteration, len(input_projects))

    projects_to_check = input_projects.difference(checked_projects)

  logger.info("%s projects - complete", len(input_projects))

  original_manifest = ET.parse(manifest_file)
  original_sha1 = create_manifest_sha1_element(original_manifest, "original")
  split_manifest = update_manifest(original_manifest, input_projects,
                                   remove_projects.keys())
  split_manifest.getroot().append(original_sha1)
  split_manifest.getroot().append(
      create_manifest_sha1_element(split_manifest, "self"))
  split_manifest.write(split_manifest_file)

  if debug_file:
    with open(debug_file, "w") as debug_fp:
      logger.info("Writing debug info to %s", debug_file)
      json.dump(
          debug_info,
          fp=debug_fp,
          sort_keys=True,
          indent=2,
          default=lambda info: info.__dict__)


def main(argv):
  try:
    opts, args = getopt.getopt(argv, "h", [
        "help",
        "debug-file=",
        "manifest=",
        "split-manifest=",
        "config=",
        "repo-list=",
        "ninja-build=",
        "ninja-binary=",
        "module-info=",
        "kati-stamp=",
        "overlay=",
    ])
  except getopt.GetoptError as err:
    print(__doc__, file=sys.stderr)
    print("**%s**" % str(err), file=sys.stderr)
    sys.exit(2)

  debug_file = None
  manifest_file = None
  split_manifest_file = None
  config_files = [DEFAULT_CONFIG_PATH]
  repo_list_file = None
  ninja_build_file = None
  module_info_file = None
  ninja_binary = "ninja"
  kati_stamp_file = None
  overlays = []

  for o, a in opts:
    if o in ("-h", "--help"):
      print(__doc__, file=sys.stderr)
      sys.exit()
    elif o in ("--debug-file"):
      debug_file = a
    elif o in ("--manifest"):
      manifest_file = a
    elif o in ("--split-manifest"):
      split_manifest_file = a
    elif o in ("--config"):
      config_files.append(a)
    elif o in ("--repo-list"):
      repo_list_file = a
    elif o in ("--ninja-build"):
      ninja_build_file = a
    elif o in ("--ninja-binary"):
      ninja_binary = a
    elif o in ("--module-info"):
      module_info_file = a
    elif o in ("--kati-stamp"):
      kati_stamp_file = a
    elif o in ("--overlay"):
      overlays.append(a)
    else:
      assert False, "unknown option \"%s\"" % o

  if not args:
    print(__doc__, file=sys.stderr)
    print("**Missing targets**", file=sys.stderr)
    sys.exit(2)
  if not manifest_file:
    print(__doc__, file=sys.stderr)
    print("**Missing required flag --manifest**", file=sys.stderr)
    sys.exit(2)
  if not split_manifest_file:
    print(__doc__, file=sys.stderr)
    print("**Missing required flag --split-manifest**", file=sys.stderr)
    sys.exit(2)
  if not module_info_file:
    module_info_file = os.path.join(os.environ["ANDROID_PRODUCT_OUT"],
                                    "module-info.json")
  if not kati_stamp_file:
    kati_stamp_file = os.path.join(
        os.environ["ANDROID_BUILD_TOP"], "out",
        ".kati_stamp-%s" % os.environ["TARGET_PRODUCT"])
  if not ninja_build_file:
    ninja_build_file = os.path.join(
        os.environ["ANDROID_BUILD_TOP"], "out",
        "combined-%s.ninja" % os.environ["TARGET_PRODUCT"])

  create_split_manifest(
      targets=args,
      manifest_file=manifest_file,
      split_manifest_file=split_manifest_file,
      config_files=config_files,
      repo_list_file=repo_list_file,
      ninja_build_file=ninja_build_file,
      ninja_binary=ninja_binary,
      module_info_file=module_info_file,
      kati_stamp_file=kati_stamp_file,
      overlays=overlays,
      debug_file=debug_file)


if __name__ == "__main__":
  main(sys.argv[1:])
