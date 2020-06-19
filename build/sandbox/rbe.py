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

"""Utilities for RBE-enabled builds."""

import os
import random
import subprocess
import tempfile

# These are the environment variables that control RBE usage with the
# --use_rbe flag. If defined on the environment, the values will be
# propagated to the build; otherwise, those defaults will be used.
TOOLS_DIR = 'prebuilts/remoteexecution-client/latest'
_RBE_ENV = {
    'USE_RBE': 'true',
    'RBE_HTTP_PROXY': '10.1.2.1:8011',
    'RBE_DIR': TOOLS_DIR,
    'NINJA_REMOTE_NUM_JOBS': '500',
    'FLAG_log_dir': 'out',
    'FLAG_server_address': 'unix:///tmp/reproxy_%s.sock' % random.randint(0,100000),
    'FLAG_exec_root': '/src',
    'FLAG_invocation_id': 'treble-%s' % random.randint(0,100000),
    'RBE_use_application_default_credentials': 'true',
    'RBE_reproxy_wait_seconds': '20',
    'RBE_output_dir': 'out',
    'RBE_proxy_log_dir': 'out',
    'RBE_cpp_dependency_scanner_plugin': os.path.join(TOOLS_DIR, 'dependency_scanner_go_plugin.so'),
    'RBE_re_proxy': os.path.join(TOOLS_DIR, 'reproxy'),
}


def get_nsjail_bin_wrapper():
  """Returns the command executed in a closed network namespace."""
  return ['netns-exec', 'rbe-closed-ns']


def environ():
  """Returns the environment variables that configure RBE."""
  env = _RBE_ENV.copy()
  for k,v in os.environ.items():
    # Environment variables take precedence over defaults.
    if k.startswith('RBE_'):
      env[k] = v
  return env


def get_env():
  """Returns a dictionary of extra environment variables"""
  return ['%s=%s' % (k,v) for k,v in environ().items()]


def get_readonlybind_mounts():
  """Returns a dictionary of readonly bind mounts"""
  creds_file = '.config/gcloud/application_default_credentials.json'
  # Bind the gcloud credentials file, if present, to authenticate.
  source_creds_file = os.path.join(os.getenv('HOME'), creds_file)
  dest_creds_file = os.path.join('/tmp', creds_file)
  if not os.path.exists(source_creds_file):
    raise IOError('Required credentials file not found: ' + source_creds_file)
  return ['%s:%s' % (source_creds_file, dest_creds_file)]


def get_extra_nsjail_args():
  """Returns a dictionary of extra nsjail.run arguments for RBE."""
  # The nsjail should be invoked in a closed network namespace.
  return ['--disable_clone_newnet']


def setup(build_log=subprocess.DEVNULL):
  """Prerequisite for having RBE enabled for the build.

  Calls RBE http proxy in a separate network namespace.

  Args:
    build_log: a file handle to write executed commands to.

  Returns:
    A cleanup function to be called after the build is done.
  """
  rbe_instance = os.getenv('RBE_instance')
  if not rbe_instance:
    raise EnvironmentError('The RBE_instance environment '
                           'variables must be defined')

  # Create the RBE http proxy whitelist file.
  rbe_service = os.getenv('RBE_service')
  if not rbe_service:
    raise EnvironmentError('The RBE_service environment '
                           'variables must be defined')
  if ':' in rbe_service:
    rbe_service = rbe_service.split(':', 1)[0]
  rbe_whitelist = [
      rbe_service,
      'oauth2.googleapis.com',
      'accounts.google.com',
  ]
  with open('/tmp/rbe_whitelist.txt', 'w+') as t:
    for w in rbe_whitelist:
      t.write(w + '\n')

  # Restart RBE http proxy.
  script_dir = os.path.dirname(os.path.abspath(__file__))
  proxy_kill_command = ['killall', 'tinyproxy']
  proxy_command = [
      'netns-exec', 'rbe-open-ns', 'tinyproxy', '-c', 'rbe_http_proxy.conf', '-d']
  rbe_proxy_log = tempfile.NamedTemporaryFile(prefix='tinyproxy_', delete=False)
  if build_log != subprocess.DEVNULL:
    print('RBE http proxy restart commands:', file=build_log)
    print(' '.join(proxy_kill_command), file=build_log)
    print('cd ' + script_dir, file=build_log)
    print(' '.join(proxy_command) + ' &> ' + rbe_proxy_log.name + ' &',
          file=build_log)
  subprocess.call(
      proxy_kill_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
  rbe_proxy = subprocess.Popen(
      proxy_command,
      cwd=script_dir,
      stdout=rbe_proxy_log,
      stderr=rbe_proxy_log)

  def cleanup():
    """Should be called after an RBE build is done."""
    if build_log != subprocess.DEVNULL:
      print('RBE http proxy kill command:', file=build_log)
      print(' '.join(proxy_kill_command), file=build_log)
    rbe_proxy.terminate()
    # TODO(diegowilson): Calling wait() sometimes dead locks.
    # Not sure if it's a tinyproxy bug or the issue described in the wait() documentation
    # https://docs.python.org/2/library/subprocess.html#subprocess.Popen.wait
    # rbe_proxy.wait()
    rbe_proxy_log.close()

  return cleanup
