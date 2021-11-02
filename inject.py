import argparse
import os
import glob
from os.path import join, isdir, dirname, isfile, dirname
import yaml
import re
import sys
import shutil
import itertools
import hashlib

QLPACK_NAME_PATTERN = re.compile('^(name:\s+)(\S+)(.*)$', re.MULTILINE)
QLPACK_VERSION_PATTERN = re.compile('^(version:\s+)(\S+)(.*)$', re.MULTILINE)
QLPACK_DEFAULTSUITEFILE_PATTERN = re.compile('^(defaultSuiteFile:\s+)(\S+)(.*)$', re.MULTILINE)


def make_key(s):
  sha1 = hashlib.sha1()
  sha1.update(s.encode('utf-8'))
  return sha1.hexdigest()


def error(msg):
  print('ERROR: ' + msg)
  sys.exit(1)


def info(msg):
  print('INFO: ' + msg)


def warning(msg):
  print('WARNING: ' + msg)


def read_file(fpath):
  with open(fpath, 'r') as f:
    return f.read()


def write_file(fpath, contents):
  with open(fpath, 'w') as f:
    f.write(contents)


def get_pack_desc(pack):
  return read_file(join(pack, 'qlpack.yml'))


def set_pack_desc(pack, desc):
  write_file(join(pack, 'qlpack.yml'), desc)


def get_pack_hash(pack):
  return read_file(join(pack, 'codeql_inject_hash.qll'))


def set_pack_hash(pack, h):
  return write_file(join(pack, 'codeql_inject_hash.qll'), h)


def get_pack_info(packdir):
  contents = get_pack_desc(packdir)
  nmatch = QLPACK_NAME_PATTERN.search(contents)
  vmatch = QLPACK_VERSION_PATTERN.search(contents)
  if not nmatch or not vmatch:
    raise Exception('Unable to parse {qlpackyml}'.format(qlpackyml=qlpackyml))
  return nmatch.group(2), vmatch.group(2)


def set_pack_info(packdir, name, version):
  contents = get_pack_desc(packdir)
  contents = re.sub(QLPACK_NAME_PATTERN, '\g<1>' + name + '\g<3>', contents)
  contents = re.sub(QLPACK_VERSION_PATTERN, '\g<1>' + version + '\g<3>', contents)
  set_pack_desc(packdir, contents)


def get_pack_default_suite(packdir):
  contents = get_pack_desc(packdir)
  match = QLPACK_DEFAULTSUITEFILE_PATTERN.search(contents)
  if not match:
    return None
  return match.group(2)


def set_pack_default_suite(packdir, default_suite):
  contents = get_pack_desc(packdir)
  if get_pack_default_suite(packdir) is None:
    contents = contents + '\ndefaultSuiteFile: ' + default_suite
  else:
    contents = re.sub(QLPACK_DEFAULTSUITEFILE_PATTERN, '\g<1>' + default_suite + '\g<3>', contents)
  set_pack_desc(packdir, contents)


def parse_version(versionstr):
  version = [int(v) for v in versionstr.split('.')]
  if len(version) != 3:
    raise Exception('Invalid length')
  return version


def version2str(version):
  return '.'.join([str(v) for v in version])


def add_versions(v1, v2):
  return [v1[i] + v2[i] for i in range(0, 3)]


def inject_import(qlpath, importname):
  IMPORT_CUSTOMIZATIONS_LIB_PATTERN = re.compile(
    '^\s*import\s+' + re.escape(importname) + '\s*$',
    re.MULTILINE
  )

  contents = read_file(qlpath)

  if IMPORT_CUSTOMIZATIONS_LIB_PATTERN.search(contents):
    info('Customizations were already injected into {qlpath}. Nothing to be done.'.format(qlpath=qlpath))
  else:
    # inject the import to the end of the file
    info('Importing {importname} into "{qlpath}" ...'.format(importname=importname, qlpath=qlpath))
    contents = contents + '\n' + 'import ' + importname
    write_file(qlpath, contents)


def parse_pattern(line):
    components = line.split(':')

    if len(components) != 2:
      raise ValueError('Invalid pattern: "' + line + '" must contain exactly one separator (:)!')

    return components


def check_patterns(patternstrings):
  try:
    result = [
      parse_pattern(p) for p in itertools.chain(
        *[re.split('\r?\n', sp) for sp in patternstrings]
      ) if p
    ]

    for qll, _ in result:
      if not isfile(qll):
        error('"{f}" is not a file!'.format(f=qll))

    return result
  except ValueError as va:
    error(va.args[0])


def inject(args):
  if not isdir(args.pack) or not isfile(join(args.pack, 'qlpack.yml')):
    error('"{pack}" is not a valid pack directory!'.format(pack=args.pack))

  # get base package information
  base_pack_name, base_pack_version = get_pack_info(args.pack)
  info('Base pack info: name: {name}, version: {version}.'.format(name=base_pack_name, version=base_pack_version))

  # check that the given default suite exists
  if not isfile(join(args.pack, args.default_suite)):
    error('"{suite}" is not a valid query suite!'.format(suite=args.default_suite))

  # parse the given version
  try:
    parse_version(args.version)
  except Exception as e:
    error(
      '"{version}" is not a proper semantic version: {errormsg}'.format(
        version=origv,
        errormsg=e.args[0]
      )
    )

  # parse given patterns
  args.patterns = check_patterns(args.patterns)
  info('---')
  info('Given Patterns:')
  info('---')
  for qll, file_pattern in args.patterns:
    info('File to inject: {qll}, files to inject into: {pattern}'.format(qll=qll, pattern=file_pattern))
  info('---')

  # copy customization files into pack and inject the given qlls
  for qll, file_pattern in args.patterns:
    qllcopyname = 'inject_{hashcode}'.format(hashcode=make_key(read_file(qll)))
    qllcopy = join(args.pack, qllcopyname + '.qll')
    if isfile(qllcopy):
      info('{f} already exists. Will not copy.'.format(f=qllcopy))
    else:
      info(
        'Copying "{fromp}" to "{top}".'.format(
          fromp=qll,
          top=qllcopy
        )
      )
      shutil.copy(qll, qllcopy)

    resolvesToFiles = False
    for t in glob.iglob(join(args.pack, file_pattern), recursive=True):
      resolvesToFiles = True
      inject_import(t, qllcopyname)
    if not resolvesToFiles:
      warning('Injection pattern "{pattern}" does not resolve to any file on disk!'.format(pattern=file_pattern))

  # set the final package name, version and default suite
  set_pack_info(args.pack, args.name, args.version)
  set_pack_default_suite(args.pack, args.default_suite)

  # create package's hash file
  info('Writing package hash...')
  sha1 = hashlib.sha1()
  for qll, file_pattern in args.patterns:
    sha1.update(read_file(qll).encode('utf-8'))
    sha1.update(file_pattern.encode('utf-8'))
  sha1.update(base_pack_version.encode('utf-8'))
  sha1.update(args.default_suite.encode('utf-8'))
  set_pack_hash(args.pack, sha1.hexdigest())


def main(args):
  parser = argparse.ArgumentParser(
    prog='inject'
  )
  parser.add_argument(
    '--pack',
    help='Path to the base pack',
    default=None
  )
  parser.add_argument(
    '--name',
    help='The name of the target pack',
    required=True
  )
  parser.add_argument(
    '--version',
    help='The version of the target pack',
    required=True
  )
  parser.add_argument(
    '--default-suite',
    help='The default query suite to execute',
    required=True
  )
  parser.add_argument(
    'patterns',
    help='Inclusion and exclusion patterns.',
    nargs='+'
  )
  inject(parser.parse_args(args))
