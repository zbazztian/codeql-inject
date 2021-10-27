import inject
import sys
import subprocess
from os.path import isfile, join
import json


codeql_exec, target_pack, name, version, patterns = sys.argv[1:]

if not isfile(codeql_exec):
  inject.error('Cannot find executable {exec}!'.format(exec=codeql_exec))


def run_impl(args):
  print(' '.join(args), flush=True)
  try:
    output = subprocess.run(
      args,
      capture_output=True,
      check=True
    ).stdout.decode()
    print(output, flush=True)
    return output
  except subprocess.CalledProcessError as cpe:
    print('Command failed with exit code: ' + str(cpe.returncode))
    print('stdout:')
    print(cpe.output.decode())
    print('stderr:')
    print(cpe.stderr.decode(), flush=True)
    raise


def run(*args):
  return run_impl(list(args))


def codeql(*args):
  args = [codeql_exec] + list(args)
  return run_impl(args)


j = json.loads(
  codeql(
    'pack', 'download',
#    '--search-path', '/adirectorywhichdoesnotexist',
#    '--additional-packs', '/adirectorywhichdoesnotexist',
#    '-vvv',
#    '--no-use-global-qlconfig',
    '--format', 'json',
    '--force',
    '--dir', 'downloaded_pack',
    target_pack
  )
)

target_pack_path = j['packs'][0]['packDir']

inject.main([
  '--pack', target_pack_path,
  '--name', name,
  '--version', version,
  '--',
  patterns
])

codeql(
  'pack', 'publish',
  '--threads', '0',
  '-vv',
  target_pack_path
)
