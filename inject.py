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


def parse_version(versionstr):
  version = [int(v) for v in versionstr.split('.')]
  if len(version) != 3:
    raise Exception('Invalid length')
  return version


def version2str(version):
  return '.'.join([str(v) for v in version])


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

  # get target package information
  packn, packv = get_pack_info(args.pack)
  packv = parse_version(packv)
  info('Target pack info: name: {name}, version: {version}.'.format(name=packn, version=version2str(packv)))

  # parse the given version
  try:
    given_version = parse_version(args.version)
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
  for qll, target_pattern in args.patterns:
    info('File to inject: {qll}, files to inject into: {pattern}'.format(qll=qll, pattern=target_pattern))
  info('---')

  # copy customization files into pack and inject the given qlls
  for qll, target_pattern in args.patterns:
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

    hasTargets = False
    for t in glob.iglob(join(args.pack, target_pattern), recursive=True):
      hasTargets = True
      inject_import(t, qllcopyname)
    if not hasTargets:
      warning('Injection pattern "{pattern}" does not resolve to any file on disk!'.format(pattern=target_pattern))

  # calculate package version by adding the given version and the target package version
  final_version = packv
  for i in range(0, 3):
    final_version[i] = final_version[i] + given_version[i]
  info('Final version is {version}.'.format(version=version2str(final_version)))

  # set the final package name and version
  set_pack_info(args.pack, args.name, version2str(final_version))


def main(args):
  parser = argparse.ArgumentParser(
    prog='inject'
  )
  parser.add_argument(
    '--pack',
    help='Path to the pack to inject into.',
    default=None
  )
  parser.add_argument(
    '--name',
    help='The name of the resulting pack',
    required=True
  )
  parser.add_argument(
    '--version',
    help='The version of the modifications (will be added to the version of the pack to be injected to)',
    required=True
  )
  parser.add_argument(
    'patterns',
    help='Inclusion and exclusion patterns.',
    nargs='+'
  )
  inject(parser.parse_args(args))
